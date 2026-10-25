"""Socle du moteur des demandes : erreurs, résultat d'une transition, verrous, événements,
enregistrement contrôlé, fichier joint, agenda et journal.

Les modules du paquet s'importent directement entre eux ; le reste de l'application passe
par la façade `workflow` (apps/approvals/workflow/__init__.py)."""

from dataclasses import dataclass, field
from typing import Any, cast

from django.core.files import File
from django.db import DataError, IntegrityError, transaction
from django.db.models import FileField, QuerySet
from django.utils.translation import gettext as _

from apps.agenda.models import CalendarEvent
from apps.approvals.kinds import kind_of
from apps.approvals.models import (
    ApprovalRequest,
    RequestEvent,
    RequestStatus,
)
from apps.core import audit, constraints
from apps.core.constraints import INVALID_VALUE
from apps.core.context import ActionContext
from apps.core.errors import ServiceError
from apps.core.files import delete_private, write_private
from apps.people.models import Employee

AUTO_APPROVAL_NO_VALIDATOR = "validation automatique : aucun valideur disponible"


AUTO_APPROVAL_TELEWORK = "validation automatique dans la limite du quota (M-02)"


class WorkflowError(ServiceError):
    """Refus d'une transition de demande (message affiché)."""


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

    request: ApprovalRequest
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


def _lock(request: ApprovalRequest) -> ApprovalRequest:
    # Verrou sur la seule ligne de la demande : le manager (nullable) est lu sans verrou.
    return (
        type(request)
        .objects.select_for_update(of=("self",))
        .select_related("requester", "requester__manager", "requester__user")
        .get(pk=request.pk)
    )


def _event(request: ApprovalRequest, actor: Employee | None, action: str, comment: str = "") -> int:
    return RequestEvent.objects.create(
        request_type=request.request_type,
        request_id=request.pk,
        actor=actor,
        action=action,
        comment=comment,
    ).pk


def _latest_event_id(request: ApprovalRequest) -> int | None:
    return (
        RequestEvent.objects.filter(request_type=request.request_type, request_id=request.pk)
        .order_by("-pk")
        .values_list("pk", flat=True)
        .first()
    )


def _lock_requester(employee_id: int) -> Employee:
    """Verrou de la fiche : deux opérations simultanées pour la même personne passent l'une
    après l'autre, et la seconde voit la demande de la première."""
    return Employee.objects.select_for_update().select_related("company").get(pk=employee_id)


# Contraintes des demandes, inscrites dans la table commune (apps/core/constraints.py).
constraints.register(
    {
        "telework_one_active_per_day": ("date", SAME_DAY),
        "transport_amount_range": ("amount", AMOUNT_RANGE),
        "transport_valid_after_month": ("month", _("La validité doit commencer au mois choisi.")),
        "leave_end_after_start": ("end", _("Le dernier jour doit être après le premier.")),
        "on_call_end_after_start": ("end", _("La fin doit être après le début.")),
    }
)


UNKNOWN_CONSTRAINT = _("La demande n'a pas pu être enregistrée : une valeur n'est pas acceptée.")


def _save_checked(request: ApprovalRequest, **kwargs: Any) -> None:
    """Enregistre sous point de sauvegarde : une contrainte de base violée malgré tout devient
    le message de cette contrainte, une valeur refusée par la base (DataError) un message
    clair ; jamais une erreur 500."""
    try:
        with transaction.atomic():
            request.save(**kwargs)
    except IntegrityError as exc:
        field, message = constraints.translate(exc, UNKNOWN_CONSTRAINT)
        raise RequestValidationError({field: message}) from exc
    except DataError as exc:
        raise RequestValidationError({None: INVALID_VALUE}) from exc


def _write_file(request: ApprovalRequest, content: File, cleanup: list[str]) -> None:
    """Écrit le fichier joint avant l'INSERT ; le nom est inscrit dans `cleanup` avant
    l'écriture (L5-18)."""
    field_name = request.file_field
    if field_name is None:
        raise ValueError("Ce type de demande n'a pas de fichier joint.")
    field = cast(FileField, request._meta.get_field(field_name))
    name = field.generate_filename(request, content.name or "justificatif")
    cleanup.append(name)
    stored = write_private(name, content)
    if stored != name:
        cleanup.append(stored)
    setattr(request, field_name, stored)


def _forget_file(request: ApprovalRequest) -> None:
    """Les fichiers ne suivent pas les transactions : un envoi annulé ne laisse pas de fichier
    sans demande (L5-05)."""
    field_file = getattr(request, request.file_field) if request.file_field else None
    if field_file and field_file.name:
        delete_private(field_file.name)


def sync_calendar(request: ApprovalRequest) -> None:
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


def _audit(
    request: ApprovalRequest, action: str, verb: str, *, context: ActionContext, extra: str = ""
) -> None:
    summary_text = _("%(verb)s : %(kind)s de %(name)s") % {
        "verb": verb,
        "kind": kind_of(request).lower,
        "name": request.requester.full_name,
    }
    if extra:
        summary_text = f"{summary_text} ({extra})"
    audit.log(
        f"requests.{action}",
        summary_text,
        actor=context.actor,
        target=request,
        request=context.request,
    )


def history(request: ApprovalRequest) -> QuerySet[RequestEvent]:
    return RequestEvent.objects.filter(
        request_type=request.request_type, request_id=request.pk
    ).select_related("actor")


def record_proof_access(request: ApprovalRequest, *, context: ActionContext) -> None:
    """Toute consultation d'un justificatif par une autre personne que le demandeur (RH,
    administrateur) est inscrite au journal d'audit, sans nom de fichier."""
    actor = context.actor
    if actor is not None and actor.pk == request.requester_id:
        return
    audit.log(
        "requests.proof_downloaded",
        _("Justificatif de transport consulté"),
        actor=actor,
        target=request,
        request=context.request,
    )
