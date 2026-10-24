"""Socle du moteur des demandes : erreurs, résultat d'une transition, verrous, événements,
enregistrement contrôlé, fichier joint, agenda et journal.

Les fonctions du paquet s'appellent par la façade `workflow` (apps/approvals/workflow/
__init__.py) : point d'entrée unique, et point de remplacement des tests."""

from dataclasses import dataclass, field

from django.db import DataError, IntegrityError, transaction
from django.utils.translation import gettext as _

from apps.agenda.models import CalendarEvent
from apps.approvals import workflow
from apps.approvals.kinds import kind_of
from apps.approvals.models import (
    ApprovalRequest,
    RequestEvent,
    RequestStatus,
)
from apps.core import audit
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


def _lock_requester(employee_id) -> Employee:
    """Verrou de la fiche : deux opérations simultanées pour la même personne passent l'une
    après l'autre, et la seconde voit la demande de la première."""
    return Employee.objects.select_for_update().select_related("company").get(pk=employee_id)


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
        field, message = workflow.CONSTRAINT_MESSAGES.get(
            workflow.constraint_name(exc), (None, workflow.UNKNOWN_CONSTRAINT)
        )
        raise workflow.RequestValidationError({field: message}) from exc
    except DataError as exc:
        raise workflow.RequestValidationError({None: workflow.INVALID_VALUE}) from exc


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


def _audit(request, actor, action, verb, *, http_request=None, extra=""):
    summary_text = _("%(verb)s : %(kind)s de %(name)s") % {
        "verb": verb,
        "kind": kind_of(request).lower,
        "name": request.requester.full_name,
    }
    if extra:
        summary_text = f"{summary_text} ({extra})"
    audit.log(f"requests.{action}", summary_text, actor=actor, target=request, request=http_request)


def history(request):
    return RequestEvent.objects.filter(
        request_type=request.request_type, request_id=request.pk
    ).select_related("actor")
