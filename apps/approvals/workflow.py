"""Moteur commun des demandes (docs/02-architecture.md, « Circuit de validation commun »).

    (envoi)          → pending                     (ou approved : validation automatique)
    pending          → approved | refused          (valideur)
    pending          → manager_approved → approved | refused   (congés d'été, étape RH)
    pending, manager_approved → cancelled          (demandeur)
    approved         → cancelled                   (RH ou administrateur, motif, L3-10)

Chaque transition :
- s'exécute dans une transaction et verrouille la demande (`select_for_update`) puis vérifie
  l'état de départ : deux clics rapides ne font qu'une transition, le second reçoit
  « Cette demande a déjà été traitée. » ;
- enregistre un RequestEvent, met à jour l'événement de calendrier, retire les notifications
  devenues fausses (e-mail pas encore parti, A3-05), crée les nouvelles, met en file les
  e-mails (45 s, annulables) et écrit le journal d'audit.

Contrôles métier (A3-02) : ceux qui dépendent des autres demandes (quota, même jour,
chevauchements, période de la campagne) sont faits ici, sous verrou de la fiche du
demandeur, à l'envoi et à chaque annulation immédiate qui rend la demande de nouveau active.
Les formulaires ne vérifient que les champs eux-mêmes. Ordre des verrous : fiche du
demandeur, puis demande.

Annulation immédiate (« Annuler » dans la notification visuelle, 30 s) : le jeton porte
l'événement créé par la transition ; elle n'est acceptée que si cet événement est toujours
le dernier de la demande (A3-01).
"""

from dataclasses import dataclass, field
from decimal import Decimal

from django.db import DataError, IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.translation import gettext as _

from apps.agenda.days import day_off, day_off_message
from apps.agenda.models import CalendarEvent
from apps.approvals import rules
from apps.approvals.kinds import kind_of, summary
from apps.approvals.models import (
    ACTIVE_STATUSES,
    LeaveRequest,
    OnCallDeclaration,
    RequestEvent,
    RequestStatus,
    SummerCampaign,
    TeleworkRequest,
    TransportProof,
)
from apps.core import audit, notifications, permissions
from apps.core.files import delete_private, write_private
from apps.core.models import Notification
from apps.people.models import IN_POST_STATUSES, Employee, Role

AUTO_APPROVAL_NO_VALIDATOR = "validation automatique : aucun valideur disponible"
AUTO_APPROVAL_TELEWORK = "validation automatique dans la limite du quota (M-02)"


class WorkflowError(Exception):
    def __init__(self, message):
        super().__init__(str(message))
        self.message = message


class RequestValidationError(WorkflowError):
    """Contrôle métier refusé : `errors` associe un champ du formulaire (ou None) au message."""

    def __init__(self, errors: dict):
        self.errors = errors
        super().__init__(next(iter(errors.values())))


ALREADY_PROCESSED = _("Cette demande a déjà été traitée.")
OTHER_DECISION = _("Une autre décision a été prise depuis. Rien n'a été modifié.")
SAME_DAY = _("Vous avez déjà une demande pour ce jour.")
AMOUNT_RANGE = _("Indiquez un montant supérieur à 0 et inférieur ou égal à 1 000 €.")
CAMPAIGN_ALREADY_OPEN = _("Une campagne est déjà ouverte.")


@dataclass
class TransitionResult:
    """Ce qu'il faut pour annuler immédiatement la transition (jeton signé de 30 s)."""

    request: object
    previous_status: str = ""
    previous_comment: str = ""
    notification_ids: list = field(default_factory=list)
    auto_approved: bool = False
    event_id: int | None = None

    def undo_payload(self, action: str) -> dict:
        return {
            "action": action,
            "type": self.request.request_type,
            "id": str(self.request.public_id),
            "event": self.event_id,
            "previous": self.previous_status,
            "comment": self.previous_comment,
            "notifications": self.notification_ids,
        }


# ---------- Qui valide ----------


def active_manager(employee: Employee):
    manager = employee.manager
    if manager is not None and manager.status in IN_POST_STATUSES:
        return manager
    return None


def hr_validators(exclude: Employee):
    """RH et administrateurs en poste, autres que le demandeur (M-12)."""
    return list(
        Employee.objects.filter(role__in=(Role.HR, Role.ADMIN), status__in=IN_POST_STATUSES)
        .exclude(pk=exclude.pk)
        .select_related("user")
    )


def is_hr_or_admin(employee) -> bool:
    return employee is not None and employee.role in (Role.HR, Role.ADMIN)


def has_hr_step(request) -> bool:
    """Congés d'été avec validation finale RH (M-03, `summer_leave_hr_step`)."""
    return (
        isinstance(request, LeaveRequest)
        and request.leave_type == LeaveRequest.LeaveType.SUMMER
        and request.company.summer_leave_hr_step
    )


def first_validators(request) -> list[Employee]:
    """Qui reçoit la demande à l'envoi : le manager direct, sinon les RH et administrateurs
    autres que le demandeur (M-12, L3-02). Types validés par les RH (transport, matériel,
    L5-04) : les RH et administrateurs autres que le demandeur."""
    if request.hr_validated:
        return hr_validators(exclude=request.requester)
    manager = active_manager(request.requester)
    if manager is not None:
        return [manager]
    return hr_validators(exclude=request.requester)


def can_decide(employee, request) -> bool:
    """Valider ou refuser maintenant : manager direct (quel que soit son profil, L1-02), ou
    RH et administrateur à sa place (M-12) ; l'étape RH des congés d'été est réservée aux RH
    et administrateurs. Personne ne décide pour soi-même."""
    if employee is None or employee.pk == request.requester_id:
        return False
    if request.hr_validated:
        return (
            request.status == RequestStatus.PENDING
            and is_hr_or_admin(employee)
            and permissions.can(employee, request.decide_action, request)
        )
    if request.status == RequestStatus.PENDING:
        manager = active_manager(request.requester)
        if manager is not None and manager.pk == employee.pk:
            return True
        return is_hr_or_admin(employee) and permissions.can(employee, "requests.decide", request)
    if request.status == RequestStatus.MANAGER_APPROVED:
        return permissions.can(employee, "requests.final_decision", request)
    return False


def can_cancel_approved(employee, request) -> bool:
    return request.status == RequestStatus.APPROVED and permissions.can(
        employee, "requests.cancel_approved", request
    )


def acting_for(employee, request):
    """Manager remplacé quand un RH ou un administrateur décide à sa place (bandeau M-12)."""
    if request.status != RequestStatus.PENDING or request.hr_validated:
        return None
    manager = active_manager(request.requester)
    if manager is not None and manager.pk != employee.pk and is_hr_or_admin(employee):
        return manager
    return None


def to_validate(employee, model):
    """Onglet « À valider » : équipe directe pour un manager ; pour les RH et administrateurs,
    seulement les personnes sans manager (M-12) et l'étape RH des congés d'été."""
    from django.db.models import Q

    related = ("requester", "requester__service", "requester__manager")
    if model.hr_validated:
        # Transport, matériel : toutes les demandes en attente, pour les RH seulement.
        if not is_hr_or_admin(employee):
            return model.objects.none()
        return (
            model.objects.filter(status=RequestStatus.PENDING)
            .exclude(requester=employee)
            .select_related(*related)
        )
    in_post_ids = Employee.objects.filter(status__in=IN_POST_STATUSES).values("pk")
    has_active_manager = Q(requester__manager_id__in=in_post_ids)
    condition = Q(status=RequestStatus.PENDING, requester__manager=employee) & has_active_manager
    if is_hr_or_admin(employee):
        condition |= Q(status=RequestStatus.PENDING) & ~has_active_manager
        if model is LeaveRequest:
            condition |= Q(status=RequestStatus.MANAGER_APPROVED)
    return (
        model.objects.filter(condition)
        .exclude(requester=employee)
        .select_related("requester", "requester__service", "requester__manager")
    )


# ---------- Effets communs ----------


def _lock(request):
    # Verrou sur la seule ligne de la demande : le manager (nullable) est lu sans verrou.
    return (
        type(request)
        .objects.select_for_update(of=("self",))
        .select_related("requester", "requester__manager", "requester__user")
        .get(pk=request.pk)
    )


def _event(request, actor, action, comment="") -> int:
    return RequestEvent.objects.create(
        request_type=request.request_type,
        request_id=request.pk,
        actor=actor,
        action=action,
        comment=comment,
    ).pk


def _latest_event_id(request):
    return (
        RequestEvent.objects.filter(request_type=request.request_type, request_id=request.pk)
        .order_by("-pk")
        .values_list("pk", flat=True)
        .first()
    )


# ---------- Contrôles métier (A3-02) ----------


def _lock_requester(employee_id) -> Employee:
    """Verrou de la fiche : deux opérations simultanées pour la même personne passent l'une
    après l'autre, et la seconde voit la demande de la première."""
    return Employee.objects.select_for_update().select_related("company").get(pk=employee_id)


def check_request(request, *, campaign=None) -> dict:
    """Contrôles qui dépendent des autres demandes du demandeur. Renvoie {champ: message}
    (vide si tout va bien). `request` peut ne pas être enregistrée (envoi) ; si elle l'est,
    elle est exclue des comptes (annulation immédiate)."""
    requester, pk = request.requester, request.pk
    if isinstance(request, TeleworkRequest):
        # Jours fériés et fermetures : pas de télétravail ces jours-là (T-16, L3-12).
        off = day_off(request.date, requester.site_id)
        if off is not None:
            return {"date": day_off_message(request.date, off)}
        same_day = TeleworkRequest.objects.filter(
            requester=requester,
            date=request.date,
            status__in=(RequestStatus.PENDING, RequestStatus.APPROVED),
        ).exclude(pk=pk)
        if same_day.exists():
            return {"date": SAME_DAY}
        quota = rules.weekly_quota(requester)
        used = rules.telework_days_in_week(requester, request.date, exclude_pk=pk)
        if used >= quota:
            return {
                "date": _(
                    "Vous avez déjà %(n)s jours de télétravail la semaine du %(week)s "
                    "(maximum %(quota)s)."
                )
                % {
                    "n": used,
                    "week": date_format(rules.monday_of(request.date), "j N"),
                    "quota": quota,
                }
            }
        return {}
    if isinstance(request, LeaveRequest):
        if request.leave_type == LeaveRequest.LeaveType.SUMMER:
            if campaign is None or campaign.status != SummerCampaign.Status.OPEN:
                return {
                    "leave_type": _(
                        "Aucune campagne de congés d'été n'est ouverte : choisissez « Autre "
                        "absence »."
                    )
                }
            if request.start < campaign.period_start or request.end > campaign.period_end:
                return {
                    "start": _(
                        "Les congés d'été de la campagne %(label)s sont compris entre le "
                        "%(a)s et le %(b)s."
                    )
                    % {
                        "label": campaign.label,
                        "a": date_format(campaign.period_start, "j F Y"),
                        "b": date_format(campaign.period_end, "j F Y"),
                    }
                }
        if rules.leave_overlaps(requester, request.start, request.end, exclude_pk=pk):
            return {"start": _("Cette période chevauche une de vos demandes existantes.")}
        return {}
    if isinstance(request, TransportProof):
        return _check_transport(request)
    if (
        isinstance(request, OnCallDeclaration)
        and request.kind == OnCallDeclaration.Kind.ON_CALL
        and rules.on_call_overlaps(requester, request.start, request.end, exclude_pk=pk)
    ):
        return {"start": _("Cette astreinte chevauche une de vos astreintes déclarées.")}
    return {}


SUBSCRIPTIONS = (TransportProof.TicketType.MONTHLY, TransportProof.TicketType.YEARLY)


def _check_transport(request) -> dict:
    """Mois dans la fenêtre acceptée (L5-07), montant dans ses bornes, et pas de chevauchement
    entre deux abonnements actifs (mensuel ou annuel, L5-06) ; un titre unique reste toujours
    possible. Contrôles du service (A3-02), refaits même si le formulaire les a déjà faits."""
    from apps.approvals.forms import transport_months

    first, last = transport_months()
    if request.month is None or not first <= request.month.replace(day=1) <= last:
        return {
            "month": _("Choisissez un mois entre %(a)s et %(b)s.")
            % {"a": date_format(first, "F Y"), "b": date_format(last, "F Y")}
        }
    if request.amount is None or not Decimal("0") < Decimal(request.amount) <= Decimal("1000"):
        return {"amount": AMOUNT_RANGE}
    if request.ticket_type not in SUBSCRIPTIONS:
        return {}
    request.compute_validity()
    overlapping = (
        TransportProof.objects.filter(
            requester=request.requester,
            ticket_type__in=SUBSCRIPTIONS,
            status__in=ACTIVE_STATUSES,
            month__lte=request.valid_until,
            valid_until__gte=request.month,
        )
        .exclude(pk=request.pk)
        .order_by("month")
        .first()
    )
    if overlapping is None:
        return {}
    covered = max(overlapping.month, request.month)
    return {
        "month": _("Un justificatif de ce type couvre déjà %(month)s.")
        % {"month": date_format(covered, "F Y")}
    }


# Contrainte de base → (champ, message) : chaque IntegrityError est traduite selon la
# contrainte en cause (L5-19), jamais par un message générique faux.
CONSTRAINT_MESSAGES = {
    "telework_one_active_per_day": ("date", SAME_DAY),
    "transport_amount_range": ("amount", AMOUNT_RANGE),
    "transport_valid_after_month": ("month", _("La validité doit commencer au mois choisi.")),
    "leave_end_after_start": ("end", _("Le dernier jour doit être après le premier.")),
    "on_call_end_after_start": ("end", _("La fin doit être après le début.")),
}
UNKNOWN_CONSTRAINT = _("La demande n'a pas pu être enregistrée : une valeur n'est pas acceptée.")
INVALID_VALUE = _("Une valeur saisie est trop longue ou invalide. Vérifiez la saisie.")


def constraint_name(exc) -> str:
    cause = exc.__cause__ or exc.__context__
    diag = getattr(cause, "diag", None)
    return getattr(diag, "constraint_name", "") or ""


def _save_checked(request, **kwargs):
    """Enregistre sous point de sauvegarde : une contrainte de base violée malgré tout devient
    le message de cette contrainte, une valeur refusée par la base (DataError) un message
    clair ; jamais une erreur 500."""
    try:
        with transaction.atomic():
            request.save(**kwargs)
    except IntegrityError as exc:
        field, message = CONSTRAINT_MESSAGES.get(constraint_name(exc), (None, UNKNOWN_CONSTRAINT))
        raise RequestValidationError({field: message}) from exc
    except DataError as exc:
        raise RequestValidationError({None: INVALID_VALUE}) from exc


def _write_file(request, content, cleanup):
    """Écrit le fichier joint avant l'INSERT ; le nom est inscrit dans `cleanup` avant
    l'écriture (L5-18)."""
    field = request._meta.get_field(request.file_field)
    name = field.generate_filename(request, content.name)
    cleanup.append(name)
    stored = write_private(name, content)
    if stored != name:
        cleanup.append(stored)
    setattr(request, request.file_field, stored)


def _forget_file(request):
    """Les fichiers ne suivent pas les transactions : un envoi annulé ne laisse pas de fichier
    sans demande (L5-05)."""
    field_file = getattr(request, request.file_field) if request.file_field else None
    if field_file and field_file.name:
        delete_private(field_file.name)


def sync_calendar(request):
    """L'événement suit la demande : en attente (hachuré) tant qu'elle est ouverte, validé à
    la validation finale, supprimé sinon."""
    events = CalendarEvent.objects.filter(source_type=request.request_type, source_id=request.pk)
    span = request.calendar_span()
    if span is None or request.status in (RequestStatus.REFUSED, RequestStatus.CANCELLED):
        events.delete()
        return
    status = (
        CalendarEvent.Status.APPROVED
        if request.status == RequestStatus.APPROVED
        else CalendarEvent.Status.PENDING
    )
    event = events.first()
    if event is None:
        CalendarEvent.objects.create(
            employee=request.requester,
            kind=request.calendar_kind,
            start=span[0],
            end=span[1],
            status=status,
            source_type=request.request_type,
            source_id=request.pk,
        )
    elif event.status != status or (event.start, event.end) != span:
        event.status, event.start, event.end = status, span[0], span[1]
        event.save(update_fields=["status", "start", "end", "updated_at"])


def _module_url(request, tab=""):
    url = reverse(kind_of(request).url_name)
    return f"{url}?onglet={tab}" if tab else url


def _notify(recipient, text, url, kind, *, email_subject="", request=None) -> int:
    return notifications.notify(
        recipient, text, url=url, kind=kind, email_subject=email_subject, source=request
    ).pk


def _notify_validators(request, validators) -> list[int]:
    kind = kind_of(request)
    text = _("%(name)s : %(kind)s à valider (%(summary)s)") % {
        "name": request.requester.full_name,
        "kind": kind.lower,
        "summary": summary(request),
    }
    return [
        _notify(
            v,
            text,
            _module_url(request, kind.todo_tab),
            Notification.Kind.REQUEST,
            email_subject=_("Demande à valider : %(kind)s") % {"kind": kind.lower},
            request=request,
        )
        for v in validators
    ]


def _notify_requester(request, verb: str, reason: str = "", *, email: bool = True) -> int:
    kind = kind_of(request)
    text = _("Votre demande (%(kind)s, %(summary)s) a été %(verb)s.") % {
        "kind": kind.lower,
        "summary": summary(request),
        "verb": verb,
    }
    if reason:
        text = f"{text} {_('Motif :')} {reason}"
    return _notify(
        request.requester,
        text,
        _module_url(request),
        Notification.Kind.DECISION,
        email_subject=_("Votre demande de %(kind)s a été %(verb)s")
        % {"kind": kind.lower, "verb": verb}
        if email
        else "",
        request=request,
    )


def _current_validators(request) -> list[Employee]:
    if request.status == RequestStatus.MANAGER_APPROVED:
        return hr_validators(request.requester)
    if request.status == RequestStatus.PENDING:
        return first_validators(request)
    return []


def _audit(request, actor, action, verb, *, http_request=None, extra=""):
    summary_text = _("%(verb)s : %(kind)s de %(name)s") % {
        "verb": verb,
        "kind": kind_of(request).lower,
        "name": request.requester.full_name,
    }
    if extra:
        summary_text = f"{summary_text} ({extra})"
    audit.log(f"requests.{action}", summary_text, actor=actor, target=request, request=http_request)


# ---------- Transitions ----------


def submit(model, requester: Employee, data: dict, *, http_request=None) -> TransitionResult:
    """Envoi (voir `_submit`). Fichier joint (L5-05, L5-18) : son nom est inscrit dans la
    liste de nettoyage avant toute écriture dans le stockage, le fichier est écrit avant
    l'INSERT, et il est supprimé si quoi que ce soit échoue ensuite (transaction annulée).
    Lève StorageUnavailableError si le stockage ne répond pas : rien n'est enregistré."""
    cleanup = []
    try:
        return _submit(model, requester, data, http_request=http_request, cleanup=cleanup)
    except Exception:
        for name in cleanup:
            delete_private(name)
        raise


@transaction.atomic
def _submit(model, requester, data, *, http_request=None, cleanup=None) -> TransitionResult:
    """Envoi. La fiche du demandeur est verrouillée, puis les contrôles métier sont faits
    (`check_request`) : deux envois simultanés ne peuvent ni dépasser le quota, ni créer deux
    demandes le même jour, ni deux absences ou astreintes qui se chevauchent. Lève
    RequestValidationError avec les messages par champ. Les congés d'été sont rattachés à
    la campagne ouverte au moment de l'envoi."""
    requester = _lock_requester(requester.pk)
    data = dict(data)
    data.pop("campaign", None)
    content = data.pop(model.file_field, None) if model.file_field else None
    request = model(requester=requester, submitted_at=timezone.now(), **data)
    campaign = None
    if isinstance(request, LeaveRequest) and request.leave_type == LeaveRequest.LeaveType.SUMMER:
        campaign = rules.open_campaign()
        request.campaign = campaign
    if isinstance(request, TransportProof):
        request.compute_validity()
    errors = check_request(request, campaign=campaign)
    if errors:
        raise RequestValidationError(errors)
    if content is not None:
        _write_file(request, content, cleanup)
    _save_checked(request)
    event_id = _event(request, requester, RequestEvent.Action.SUBMITTED)
    result = TransitionResult(request, previous_status="", event_id=event_id)

    validators = first_validators(request)
    company = requester.company
    if not validators:
        result.event_id = _approve_automatically(request, AUTO_APPROVAL_NO_VALIDATOR, http_request)
        result.auto_approved = True
    elif isinstance(request, TeleworkRequest) and company.telework_auto_approve:
        result.event_id = _approve_automatically(request, AUTO_APPROVAL_TELEWORK, http_request)
        result.auto_approved = True
    else:
        sync_calendar(request)
        result.notification_ids = _notify_validators(request, validators)
        _audit(request, requester, "submitted", _("Demande envoyée"), http_request=http_request)
    return result


def _approve_automatically(request, reason, http_request):
    request.status = RequestStatus.APPROVED
    request.decided_at = timezone.now()
    request.decision_comment = reason
    request.save(update_fields=["status", "decided_at", "decision_comment", "updated_at"])
    event_id = _event(request, None, RequestEvent.Action.AUTO_APPROVED, reason)
    sync_calendar(request)
    _audit(
        request,
        None,
        "auto_approved",
        _("Demande validée"),
        http_request=http_request,
        extra=reason,
    )
    return event_id


@transaction.atomic
def approve(request, actor: Employee, *, comment: str = "", http_request=None) -> TransitionResult:
    request = _lock(request)
    if request.status not in (RequestStatus.PENDING, RequestStatus.MANAGER_APPROVED):
        raise WorkflowError(ALREADY_PROCESSED)
    if not can_decide(actor, request):
        raise WorkflowError(_("Vous ne pouvez pas valider cette demande."))
    result = TransitionResult(request, previous_status=request.status)
    now = timezone.now()
    first_step = request.status == RequestStatus.PENDING
    # Étape manager des congés d'été : seulement si le valideur n'est ni RH ni administrateur
    # (L3-03) et que le demandeur a un manager (L3-02).
    if first_step and has_hr_step(request) and not is_hr_or_admin(actor):
        request.status = RequestStatus.MANAGER_APPROVED
        request.manager_decided_by, request.manager_decided_at = actor, now
        request.save(
            update_fields=["status", "manager_decided_by", "manager_decided_at", "updated_at"]
        )
        result.event_id = _event(request, actor, RequestEvent.Action.MANAGER_APPROVED, comment)
        sync_calendar(request)
        notifications.retract_unsent(request)
        # L3-13 : le demandeur est prévenu dans Dianna seulement ; les RH reçoivent l'e-mail.
        result.notification_ids = [
            _notify_requester(request, _("validée par votre manager"), email=False)
        ]
        result.notification_ids += _notify_validators(request, hr_validators(request.requester))
        _audit(
            request,
            actor,
            "manager_approved",
            _("Validée par le manager"),
            http_request=http_request,
        )
        return result
    if first_step and isinstance(request, LeaveRequest):
        request.manager_decided_by, request.manager_decided_at = actor, now
    request.status = RequestStatus.APPROVED
    request.decided_by, request.decided_at, request.decision_comment = actor, now, comment
    request.save()
    result.event_id = _event(request, actor, RequestEvent.Action.APPROVED, comment)
    sync_calendar(request)
    notifications.retract_unsent(request)
    result.notification_ids = [_notify_requester(request, _("validée"))]
    _audit(
        request,
        actor,
        "approved",
        _("Demande validée"),
        http_request=http_request,
        extra=_substitution(request, actor, first_step),
    )
    return result


def _substitution(request, actor, first_step) -> str:
    """Trace d'un remplacement du manager par un RH ou un administrateur (M-12)."""
    manager = active_manager(request.requester)
    if first_step and manager is not None and manager.pk != actor.pk:
        return _("à la place de %(name)s") % {"name": manager.full_name}
    return ""


@transaction.atomic
def refuse(request, actor: Employee, *, reason: str, http_request=None) -> TransitionResult:
    reason = (reason or "").strip()
    if not reason:
        raise WorkflowError(_("Indiquez le motif du refus."))
    request = _lock(request)
    if request.status not in (RequestStatus.PENDING, RequestStatus.MANAGER_APPROVED):
        raise WorkflowError(ALREADY_PROCESSED)
    if not can_decide(actor, request):
        raise WorkflowError(_("Vous ne pouvez pas refuser cette demande."))
    result = TransitionResult(request, previous_status=request.status)
    request.status = RequestStatus.REFUSED
    request.decided_by, request.decided_at = actor, timezone.now()
    request.decision_comment = reason
    request.save()
    result.event_id = _event(request, actor, RequestEvent.Action.REFUSED, reason)
    sync_calendar(request)
    notifications.retract_unsent(request)
    result.notification_ids = [_notify_requester(request, _("refusée"), reason)]
    _audit(
        request,
        actor,
        "refused",
        _("Demande refusée"),
        http_request=http_request,
        extra=_substitution(request, actor, result.previous_status == RequestStatus.PENDING),
    )
    return result


@transaction.atomic
def cancel(request, actor: Employee, *, http_request=None) -> TransitionResult:
    """Le demandeur annule une demande encore en attente (y compris en attente de l'étape RH)."""
    request = _lock(request)
    if request.requester_id != actor.pk:
        raise WorkflowError(_("Seul le demandeur peut annuler cette demande."))
    if request.status not in (RequestStatus.PENDING, RequestStatus.MANAGER_APPROVED):
        raise WorkflowError(ALREADY_PROCESSED)
    result = TransitionResult(request, previous_status=request.status)
    request.status = RequestStatus.CANCELLED
    request.save(update_fields=["status", "updated_at"])
    result.event_id = _event(request, actor, RequestEvent.Action.CANCELLED)
    sync_calendar(request)
    notifications.retract_unsent(request)  # « Demande à valider » chez le valideur (A3-05)
    _audit(request, actor, "cancelled", _("Demande annulée"), http_request=http_request)
    return result


@transaction.atomic
def cancel_approved(
    request, actor: Employee, *, reason: str, http_request=None
) -> TransitionResult:
    """RH ou administrateur : annulation d'une demande validée, motif obligatoire (L3-10)."""
    reason = (reason or "").strip()
    if not reason:
        raise WorkflowError(_("Indiquez le motif de l'annulation."))
    request = _lock(request)
    if request.status != RequestStatus.APPROVED:
        raise WorkflowError(ALREADY_PROCESSED)
    if not can_cancel_approved(actor, request):
        raise WorkflowError(_("Vous ne pouvez pas annuler cette demande."))
    result = TransitionResult(
        request, previous_status=request.status, previous_comment=request.decision_comment
    )
    request.status = RequestStatus.CANCELLED
    request.decision_comment = reason
    request.save(update_fields=["status", "decision_comment", "updated_at"])
    result.event_id = _event(request, actor, RequestEvent.Action.CANCELLED, reason)
    sync_calendar(request)
    notifications.retract_unsent(request)
    result.notification_ids = [_notify_requester(request, _("annulée"), reason)]
    _audit(
        request,
        actor,
        "cancelled_approved",
        _("Demande validée annulée"),
        http_request=http_request,
    )
    return result


# ---------- Annulation immédiate (30 s, auteur seulement) ----------


REACTIVATING = ("refuse", "cancel", "cancel_approved")


@transaction.atomic
def undo(model, payload: dict, actor: Employee, *, http_request=None):
    """Défait la dernière transition de son auteur, seulement si l'événement qu'elle a créé
    est toujours le dernier de la demande : sinon « Une autre décision a été prise depuis »
    et rien n'est modifié (A3-01). Après un envoi : la demande, son événement et ses
    notifications sont supprimés ; le journal garde « demande envoyée puis retirée » (L1-08).
    Après une décision : l'état précédent est rétabli ; si la demande redevient active
    (refus ou annulation défaits), les contrôles métier sont refaits sous verrou (A3-02)."""
    found = model.objects.filter(public_id=payload["id"]).values_list("requester_id").first()
    if found is None:
        raise WorkflowError(ALREADY_PROCESSED)
    action = payload["action"]
    if action in REACTIVATING:
        _lock_requester(found[0])
    request = (
        model.objects.select_for_update(of=("self",))
        .select_related("requester", "requester__manager", "requester__company")
        .filter(public_id=payload["id"])
        .first()
    )
    if request is None:
        raise WorkflowError(ALREADY_PROCESSED)
    if payload.get("event") is None or _latest_event_id(request) != payload["event"]:
        raise WorkflowError(OTHER_DECISION)
    if action == "submit":
        if request.requester_id != actor.pk:
            raise WorkflowError(ALREADY_PROCESSED)
        Notification.objects.filter(source_type=request.request_type, source_id=request.pk).delete()
        CalendarEvent.objects.filter(
            source_type=request.request_type, source_id=request.pk
        ).delete()
        RequestEvent.objects.filter(
            request_type=request.request_type, request_id=request.pk
        ).delete()
        _audit(
            request,
            actor,
            "withdrawn",
            _("Demande envoyée puis retirée"),
            http_request=http_request,
        )
        request.delete()
        if request.file_field:
            # Justificatif retiré dans les 30 s : supprimé une fois l'annulation validée (L5-05).
            transaction.on_commit(lambda: _forget_file(request))
        return None
    previous = payload["previous"]
    expected = {
        "approve": (RequestStatus.APPROVED, RequestStatus.MANAGER_APPROVED),
        "refuse": (RequestStatus.REFUSED,),
        "cancel": (RequestStatus.CANCELLED,),
        "cancel_approved": (RequestStatus.CANCELLED,),
    }[action]
    if request.status not in expected or previous not in ACTIVE_STATUSES:
        raise WorkflowError(ALREADY_PROCESSED)
    request.status = previous
    if action == "cancel_approved":
        request.decision_comment = payload.get("comment", "")
    elif action in ("approve", "refuse"):
        request.decided_by, request.decided_at, request.decision_comment = None, None, ""
        if previous == RequestStatus.PENDING and isinstance(request, LeaveRequest):
            request.manager_decided_by, request.manager_decided_at = None, None
    if action in REACTIVATING:
        errors = check_request(request, campaign=getattr(request, "campaign", None))
        if errors:
            raise WorkflowError(next(iter(errors.values())))
    try:
        _save_checked(request)
    except RequestValidationError as error:
        raise WorkflowError(error.message) from error
    Notification.objects.filter(
        pk__in=payload.get("notifications", []),
        source_type=request.request_type,
        source_id=request.pk,
    ).delete()
    notifications.retract_unsent(request)
    _event(request, actor, RequestEvent.Action.REVERTED)
    sync_calendar(request)
    # La transition défaite avait retiré « Demande à valider » : les valideurs actuels sont
    # de nouveau prévenus.
    if request.status != RequestStatus.APPROVED:
        _notify_validators(request, _current_validators(request))
    _audit(request, actor, "reverted", _("Décision annulée"), http_request=http_request)
    return request


# ---------- Campagnes de congés d'été (RH) ----------


CAMPAIGN_FIELDS = ("label", "period_start", "period_end", "deadline", "conflict_threshold")


@transaction.atomic
def create_summer_campaign(data: dict, actor, *, http_request=None):
    """Crée une campagne en brouillon et l'inscrit au journal d'audit."""
    campaign = SummerCampaign.objects.create(
        **{name: data[name] for name in CAMPAIGN_FIELDS if name in data}
    )
    audit.log(
        "requests.campaign_created",
        _("Campagne créée : %(l)s") % {"l": campaign.label},
        actor=actor,
        target=campaign,
        request=http_request,
    )
    return campaign


@transaction.atomic
def open_summer_campaign(campaign, actor, *, http_request=None):
    """Ouvre une campagne. Toutes les campagnes de l'entreprise sont verrouillées : deux
    ouvertures simultanées donnent une seule campagne ouverte (A3-06)."""
    campaigns = {c.pk: c for c in SummerCampaign.objects.select_for_update().order_by("pk")}
    campaign = campaigns.get(campaign.pk)
    if campaign is None or campaign.status != SummerCampaign.Status.DRAFT:
        raise WorkflowError(_("Cette campagne ne peut pas être ouverte."))
    if any(c.status == SummerCampaign.Status.OPEN for c in campaigns.values()):
        raise WorkflowError(CAMPAIGN_ALREADY_OPEN)
    campaign.status = SummerCampaign.Status.OPEN
    try:
        with transaction.atomic():
            campaign.save(update_fields=["status", "updated_at"])
    except IntegrityError as exc:
        raise WorkflowError(CAMPAIGN_ALREADY_OPEN) from exc
    _campaign_audit(campaign, actor, _("Campagne ouverte"), http_request)
    return campaign


@transaction.atomic
def close_summer_campaign(campaign, actor, *, http_request=None):
    campaign = SummerCampaign.objects.select_for_update().filter(pk=campaign.pk).first()
    if campaign is None or campaign.status != SummerCampaign.Status.OPEN:
        raise WorkflowError(_("Cette campagne n'est pas ouverte."))
    campaign.status = SummerCampaign.Status.CLOSED
    campaign.save(update_fields=["status", "updated_at"])
    _campaign_audit(campaign, actor, _("Campagne close"), http_request)
    return campaign


def _campaign_audit(campaign, actor, title, http_request):
    audit.log(
        f"requests.campaign_{campaign.status}",
        f"{title} : {campaign.label}",
        actor=actor,
        target=campaign,
        request=http_request,
    )


def history(request):
    return RequestEvent.objects.filter(
        request_type=request.request_type, request_id=request.pk
    ).select_related("actor")
