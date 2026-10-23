"""Services du matériel (docs/modules/07-materiel.md).

Chaque action verrouille l'équipement (`select_for_update`), vérifie son état, écrit
l'historique (`EquipmentEvent`), crée la notification et l'entrée du journal d'audit. Un seul
détenteur à la fois (L5-08) : deux attributions simultanées du même équipement donnent une
attribution et un message, jamais une erreur 500 (contraintes de base en dernier rempart)."""

import unicodedata

from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from apps.core import audit, notifications
from apps.core.models import Notification
from apps.equipment.models import (
    EquipmentAssignment,
    EquipmentEvent,
    EquipmentIssue,
    EquipmentItem,
    EquipmentRequest,
)
from apps.people.models import IN_POST_STATUSES, Employee, Role

Status = EquipmentItem.Status
SERIAL_TAKEN = gettext_lazy("Ce numéro de série existe déjà dans le parc.")
ALREADY_ASSIGNED = gettext_lazy("Cet équipement est déjà attribué.")
NOT_AVAILABLE = gettext_lazy("Cet équipement n'est plus disponible.")
CHANGED = gettext_lazy("Cet équipement a changé d'état entre-temps. Rien n'a été modifié.")


class EquipmentError(Exception):
    def __init__(self, message, field=None):
        super().__init__(str(message))
        self.message = message
        self.field = field


# Contrainte de base → (message, champ) : chaque IntegrityError est traduite selon la
# contrainte en cause (L5-19).
CONSTRAINT_MESSAGES = {
    "equipment_serial_unique": (SERIAL_TAKEN, "serial_number"),
    "equipment_one_open_assignment": (ALREADY_ASSIGNED, None),
    "equipment_one_assignment_per_request": (
        gettext_lazy("Un équipement a déjà été attribué pour cette demande."),
        None,
    ),
    "equipment_holder_matches_status": (CHANGED, None),
}


def _integrity_error(exc) -> EquipmentError:
    from apps.approvals.workflow import constraint_name

    message, field = CONSTRAINT_MESSAGES.get(
        constraint_name(exc),
        (gettext_lazy("L'opération n'a pas pu être enregistrée. Réessayez."), None),
    )
    return EquipmentError(message, field)


def _lock(item) -> EquipmentItem:
    return (
        EquipmentItem.objects.select_for_update(of=("self",))
        .select_related("holder")
        .get(pk=item.pk)
    )


def _event(item, action, actor, employee=None, comment="") -> int:
    return EquipmentEvent.objects.create(
        item=item, action=action, actor=actor, employee=employee, comment=comment
    ).pk


def _label(item) -> str:
    return f"{item.get_kind_display()} {item.serial_number}"


def _hr():
    """RH en poste avec un compte ; à défaut, les administrateurs (signalements)."""
    people = Employee.objects.filter(status__in=IN_POST_STATUSES, user__is_active=True)
    return list(people.filter(role=Role.HR)) or list(people.filter(role=Role.ADMIN))


# ---------- Parc ----------


def normalize_serial(value: str) -> str:
    """Numéro de série normalisé (L5-09) : Unicode NFKC (« ＡＢ » devient « AB »), sans aucun
    espace (espaces insécables compris), en majuscules."""
    return "".join(unicodedata.normalize("NFKC", value or "").split()).upper()


@transaction.atomic
def add_item(*, kind, model, serial_number, actor, request=None) -> EquipmentItem:
    """Numéro de série normalisé, puis unique dans l'entreprise (contrainte de base sur la
    valeur normalisée)."""
    serial_number = normalize_serial(serial_number)
    if not serial_number:
        raise EquipmentError(_("Indiquez le numéro de série."), "serial_number")
    if EquipmentItem.objects.filter(serial_number=serial_number).exists():
        raise EquipmentError(SERIAL_TAKEN, "serial_number")
    try:
        with transaction.atomic():
            item = EquipmentItem.objects.create(kind=kind, model=model, serial_number=serial_number)
    except IntegrityError as exc:
        raise _integrity_error(exc) from exc
    _event(item, EquipmentEvent.Action.ADDED, actor)
    audit.log(
        "equipment.added",
        _("Équipement ajouté au parc : %(item)s") % {"item": _label(item)},
        actor=actor,
        target=item,
        request=request,
    )
    return item


@transaction.atomic
def assign(item, employee, *, actor, equipment_request=None, request=None) -> dict:
    """Attribue un équipement en stock. Renvoie ce qu'il faut pour l'annulation immédiate."""
    item = _lock(item)
    if item.status == Status.ASSIGNED or item.holder_id:
        raise EquipmentError(ALREADY_ASSIGNED)
    if item.status != Status.IN_STOCK:
        raise EquipmentError(NOT_AVAILABLE)
    if employee.status not in IN_POST_STATUSES:
        raise EquipmentError(_("Cette personne n'est plus en poste."), "employee")
    if equipment_request is not None:
        equipment_request = EquipmentRequest.objects.select_for_update().get(
            pk=equipment_request.pk
        )
        if equipment_request.status != "approved" or equipment_request.kind != item.kind:
            raise EquipmentError(_("Cette demande ne peut pas recevoir cet équipement."))
        if equipment_request.assignments.exists():
            raise EquipmentError(_("Un équipement a déjà été attribué pour cette demande."))
    now = timezone.now()
    try:
        with transaction.atomic():
            assignment = EquipmentAssignment.objects.create(
                item=item,
                employee=employee,
                assigned_at=now,
                assigned_by=actor,
                request=equipment_request,
            )
    except IntegrityError as exc:
        raise _integrity_error(exc) from exc
    item.status, item.holder, item.assigned_at = Status.ASSIGNED, employee, now
    item.save(update_fields=["status", "holder", "assigned_at", "updated_at"])
    event_id = _event(item, EquipmentEvent.Action.ASSIGNED, actor, employee)
    note = notifications.notify(
        employee,
        _("Un équipement vous a été attribué : %(kind)s %(model)s")
        % {"kind": item.get_kind_display(), "model": item.model},
        url="/materiel/",
    )
    audit.log(
        "equipment.assigned",
        _("%(item)s attribué à %(name)s") % {"item": _label(item), "name": employee.full_name},
        actor=actor,
        target=item,
        request=request,
    )
    return {
        "item": str(item.public_id),
        "assignment": assignment.pk,
        "event": event_id,
        "notification": note.pk,
    }


@transaction.atomic
def undo_assign(payload: dict, *, actor, request=None) -> EquipmentItem:
    """« Annuler » après une attribution (30 s, auteur seulement) : l'équipement revient en
    stock, l'attribution et la notification disparaissent. Refusé si l'équipement a changé
    depuis (dernier événement différent)."""
    item = EquipmentItem.objects.filter(public_id=payload["item"]).first()
    if item is None:
        raise EquipmentError(CHANGED)
    item = _lock(item)
    latest = item.events.order_by("-pk").values_list("pk", flat=True).first()
    assignment = EquipmentAssignment.objects.filter(
        pk=payload["assignment"], item=item, returned_at__isnull=True
    ).first()
    if latest != payload["event"] or assignment is None or item.status != Status.ASSIGNED:
        raise EquipmentError(CHANGED)
    employee = assignment.employee
    assignment.delete()
    Notification.objects.filter(pk=payload["notification"], recipient=employee).delete()
    item.status, item.holder, item.assigned_at = Status.IN_STOCK, None, None
    item.save(update_fields=["status", "holder", "assigned_at", "updated_at"])
    _event(item, EquipmentEvent.Action.UNDONE, actor, employee)
    audit.log(
        "equipment.assignment_undone",
        _("Attribution annulée : %(item)s") % {"item": _label(item)},
        actor=actor,
        target=item,
        request=request,
    )
    return item


def _close_assignment(item, now):
    EquipmentAssignment.objects.filter(item=item, returned_at__isnull=True).update(
        returned_at=now, updated_at=now
    )


@transaction.atomic
def return_item(item, *, actor, request=None) -> EquipmentItem:
    """Restitution : l'équipement repasse en stock, l'attribution est fermée."""
    item = _lock(item)
    if item.status != Status.ASSIGNED:
        raise EquipmentError(CHANGED)
    holder, now = item.holder, timezone.now()
    _close_assignment(item, now)
    item.status, item.holder, item.assigned_at = Status.IN_STOCK, None, None
    item.save(update_fields=["status", "holder", "assigned_at", "updated_at"])
    _event(item, EquipmentEvent.Action.RETURNED, actor, holder)
    audit.log(
        "equipment.returned",
        _("Restitution enregistrée : %(item)s") % {"item": _label(item)},
        actor=actor,
        target=item,
        request=request,
    )
    return item


@transaction.atomic
def send_to_repair(item, *, actor, comment="", request=None) -> dict:
    """En stock ou attribué → en réparation ; le détenteur éventuel est conservé (L5-10).
    Renvoie ce qu'il faut pour l'annulation immédiate (30 s)."""
    item = _lock(item)
    if item.status not in (Status.IN_STOCK, Status.ASSIGNED):
        raise EquipmentError(CHANGED)
    previous = item.status
    item.status = Status.REPAIR
    item.save(update_fields=["status", "updated_at"])
    event_id = _event(item, EquipmentEvent.Action.REPAIR, actor, item.holder, comment)
    audit.log(
        "equipment.repair",
        _("Envoyé en réparation : %(item)s") % {"item": _label(item)},
        actor=actor,
        target=item,
        request=request,
    )
    return {"item": str(item.public_id), "event": event_id, "previous": previous}


@transaction.atomic
def undo_repair(payload: dict, *, actor, request=None) -> EquipmentItem:
    """« Annuler » après un envoi en réparation (30 s, auteur seulement) : l'équipement
    reprend son état précédent ; l'historique garde « Envoyé en réparation » et ajoute « Envoi
    en réparation annulé », comme une attribution annulée. Refusé si l'équipement a changé
    depuis, donc aussi pour un jeton déjà utilisé (le dernier événement n'est plus le même)."""
    item = EquipmentItem.objects.filter(public_id=payload["item"]).first()
    if item is None:
        raise EquipmentError(CHANGED)
    item = _lock(item)
    latest = item.events.order_by("-pk").values_list("pk", flat=True).first()
    previous = payload["previous"]
    if (
        latest != payload["event"]
        or item.status != Status.REPAIR
        or previous not in (Status.IN_STOCK, Status.ASSIGNED)
        or (previous == Status.ASSIGNED) != bool(item.holder_id)
    ):
        raise EquipmentError(CHANGED)
    item.status = previous
    item.save(update_fields=["status", "updated_at"])
    _event(item, EquipmentEvent.Action.REPAIR_UNDONE, actor, item.holder)
    audit.log(
        "equipment.repair_undone",
        _("Envoi en réparation annulé : %(item)s") % {"item": _label(item)},
        actor=actor,
        target=item,
        request=request,
    )
    return item


@transaction.atomic
def back_from_repair(item, *, actor, request=None) -> EquipmentItem:
    """Fin de réparation : rendu à son détenteur s'il en a un, sinon remis en stock (L5-10)."""
    item = _lock(item)
    if item.status != Status.REPAIR:
        raise EquipmentError(CHANGED)
    item.status = Status.ASSIGNED if item.holder_id else Status.IN_STOCK
    item.save(update_fields=["status", "updated_at"])
    _event(item, EquipmentEvent.Action.BACK, actor, item.holder)
    audit.log(
        "equipment.back",
        _("Retour de réparation : %(item)s") % {"item": _label(item)},
        actor=actor,
        target=item,
        request=request,
    )
    return item


@transaction.atomic
def retire(item, *, actor, request=None) -> EquipmentItem:
    """Retirer du parc : seulement un équipement sans détenteur, en stock ou en réparation."""
    item = _lock(item)
    if item.status not in (Status.IN_STOCK, Status.REPAIR) or item.holder_id:
        raise EquipmentError(
            _("Seul un équipement en stock ou en réparation, sans détenteur, peut être retiré.")
        )
    item.status = Status.RETIRED
    item.save(update_fields=["status", "updated_at"])
    _event(item, EquipmentEvent.Action.RETIRED, actor)
    audit.log(
        "equipment.retired",
        _("Retiré du parc : %(item)s") % {"item": _label(item)},
        actor=actor,
        target=item,
        request=request,
    )
    return item


# ---------- Signalements ----------


@transaction.atomic
def report_issue(item, *, reporter, description, request=None) -> EquipmentIssue:
    """« Signaler un problème » : par le détenteur ; les RH sont prévenus."""
    item = _lock(item)
    if item.holder_id != reporter.pk:
        raise EquipmentError(_("Vous ne détenez pas cet équipement."))
    issue = EquipmentIssue.objects.create(item=item, reported_by=reporter, description=description)
    _event(item, EquipmentEvent.Action.ISSUE, reporter, reporter, description)
    text = _("%(name)s signale un problème : %(item)s") % {
        "name": reporter.full_name,
        "item": _label(item),
    }
    for person in _hr():
        notifications.notify(person, text, url="/materiel/?onglet=signalements")
    audit.log(
        "equipment.issue_reported",
        _("Problème signalé : %(item)s") % {"item": _label(item)},
        actor=reporter,
        target=item,
        request=request,
    )
    return issue


def _lock_issue(issue) -> EquipmentIssue:
    issue = EquipmentIssue.objects.select_for_update().get(pk=issue.pk)
    if issue.status != EquipmentIssue.Status.OPEN:
        raise EquipmentError(_("Ce signalement est déjà clos."))
    return issue


@transaction.atomic
def close_issue(issue, *, actor, resolution, request=None) -> EquipmentIssue:
    issue = _lock_issue(issue)
    issue.status = EquipmentIssue.Status.CLOSED
    issue.closed_by, issue.closed_at, issue.resolution = actor, timezone.now(), resolution
    issue.save(update_fields=["status", "closed_by", "closed_at", "resolution", "updated_at"])
    _event(issue.item, EquipmentEvent.Action.ISSUE_CLOSED, actor, issue.reported_by, resolution)
    notifications.notify(
        issue.reported_by,
        _("Votre signalement (%(item)s) est clos : %(resolution)s")
        % {"item": _label(issue.item), "resolution": resolution},
        url="/materiel/",
    )
    audit.log(
        "equipment.issue_closed",
        _("Signalement clos : %(item)s") % {"item": _label(issue.item)},
        actor=actor,
        target=issue.item,
        request=request,
    )
    return issue


@transaction.atomic
def issue_to_repair(issue, *, actor, request=None) -> dict:
    """« Envoyer en réparation » depuis un signalement : le détenteur est conservé."""
    issue = _lock_issue(issue)
    return send_to_repair(issue.item, actor=actor, comment=issue.description, request=request)


# ---------- Archivage d'un salarié ----------


def held_by(employee) -> list:
    return list(
        EquipmentItem.objects.filter(holder=employee)
        .exclude(status=Status.RETIRED)
        .order_by("kind", "serial_number")
    )


def alert_hr_on_departure(employee, *, actor) -> int:
    """Archivage d'un détenteur : il n'est pas bloqué (L5-11) ; les RH reçoivent la liste du
    matériel à restituer."""
    items = held_by(employee)
    if not items:
        return 0
    text = _("%(name)s est archivé et détient encore : %(items)s. Pensez à la restitution.") % {
        "name": employee.full_name,
        "items": ", ".join(_label(i) for i in items),
    }
    if len(text) > 255:
        text = text[:254] + "…"
    recipients = [p for p in _hr() if actor is None or p.pk != actor.pk] or _hr()
    for person in recipients:
        notifications.notify(person, text, url="/materiel/?onglet=parc")
    return len(items)
