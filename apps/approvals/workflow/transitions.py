"""Transitions d'une demande : envoi, validation, refus, annulation.

Les modules du paquet s'importent directement entre eux ; le reste de l'application passe
par la façade `workflow` (apps/approvals/workflow/__init__.py)."""

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.approvals import rules
from apps.approvals.models import (
    LeaveRequest,
    RequestEvent,
    RequestStatus,
    TeleworkRequest,
    TransportProof,
)
from apps.approvals.workflow.checks import check_request
from apps.approvals.workflow.common import (
    ALREADY_PROCESSED,
    AUTO_APPROVAL_NO_VALIDATOR,
    AUTO_APPROVAL_TELEWORK,
    RequestValidationError,
    TransitionResult,
    WorkflowError,
    _audit,
    _event,
    _lock,
    _lock_requester,
    _save_checked,
    _write_file,
    sync_calendar,
)
from apps.approvals.workflow.notifications import _notify_requester, _notify_validators
from apps.approvals.workflow.validators import (
    active_manager,
    can_cancel_approved,
    can_decide,
    first_validators,
    has_hr_step,
    hr_validators,
    is_hr_or_admin,
)
from apps.core import notifications
from apps.core.context import ActionContext
from apps.core.files import delete_private


def submit(model, data: dict, *, context: ActionContext) -> TransitionResult:
    """Envoi (voir `_submit`). Fichier joint (L5-05, L5-18) : son nom est inscrit dans la
    liste de nettoyage avant toute écriture dans le stockage, le fichier est écrit avant
    l'INSERT, et il est supprimé si quoi que ce soit échoue ensuite (transaction annulée).
    Lève StorageUnavailableError si le stockage ne répond pas : rien n'est enregistré."""
    context.person()
    cleanup: list[str] = []
    try:
        return _submit(model, data, context=context, cleanup=cleanup)
    except Exception:
        for name in cleanup:
            delete_private(name)
        raise


@transaction.atomic
def _submit(model, data, *, context: ActionContext, cleanup) -> TransitionResult:
    """Envoi. La fiche du demandeur est verrouillée, puis les contrôles métier sont faits
    (`check_request`) : deux envois simultanés ne peuvent ni dépasser le quota, ni créer deux
    demandes le même jour, ni deux absences ou astreintes qui se chevauchent. Lève
    RequestValidationError avec les messages par champ. Les congés d'été sont rattachés à
    la campagne ouverte au moment de l'envoi."""
    requester = _lock_requester(context.person().pk)
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
        result.event_id = _approve_automatically(request, AUTO_APPROVAL_NO_VALIDATOR, context)
        result.auto_approved = True
    elif isinstance(request, TeleworkRequest) and company.telework_auto_approve:
        result.event_id = _approve_automatically(request, AUTO_APPROVAL_TELEWORK, context)
        result.auto_approved = True
    else:
        sync_calendar(request)
        result.notification_ids = _notify_validators(request, validators)
        _audit(request, "submitted", _("Demande envoyée"), context=context)
    return result


def _approve_automatically(request, reason: str, context: ActionContext) -> int:
    """Validation sans valideur : le journal n'a pas d'auteur, mais garde l'adresse."""
    request.status = RequestStatus.APPROVED
    request.decided_at = timezone.now()
    request.decision_comment = reason
    request.save(update_fields=["status", "decided_at", "decision_comment", "updated_at"])
    event_id = _event(request, None, RequestEvent.Action.AUTO_APPROVED, reason)
    sync_calendar(request)
    _audit(
        request,
        "auto_approved",
        _("Demande validée"),
        context=ActionContext(None, context.request),
        extra=reason,
    )
    return event_id


@transaction.atomic
def approve(request, *, context: ActionContext, comment: str = "") -> TransitionResult:
    actor = context.person()
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
        _audit(request, "manager_approved", _("Validée par le manager"), context=context)
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
        "approved",
        _("Demande validée"),
        context=context,
        extra=_substitution(request, actor, first_step),
    )
    return result


def _substitution(request, actor, first_step) -> str:
    """Trace d'un remplacement du manager par un RH ou un administrateur (M-12). Jamais pour
    les types validés par les RH, dont ils sont les valideurs prévus (L5-04)."""
    if request.hr_validated:
        return ""
    manager = active_manager(request.requester)
    if first_step and manager is not None and manager.pk != actor.pk:
        return _("à la place de %(name)s") % {"name": manager.full_name}
    return ""


@transaction.atomic
def refuse(request, *, context: ActionContext, reason: str) -> TransitionResult:
    actor = context.person()
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
        "refused",
        _("Demande refusée"),
        context=context,
        extra=_substitution(request, actor, result.previous_status == RequestStatus.PENDING),
    )
    return result


@transaction.atomic
def cancel(request, *, context: ActionContext) -> TransitionResult:
    """Le demandeur annule une demande encore en attente (y compris en attente de l'étape RH)."""
    actor = context.person()
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
    _audit(request, "cancelled", _("Demande annulée"), context=context)
    return result


@transaction.atomic
def cancel_approved(request, *, context: ActionContext, reason: str) -> TransitionResult:
    """RH ou administrateur : annulation d'une demande validée, motif obligatoire (L3-10)."""
    actor = context.person()
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
    _audit(request, "cancelled_approved", _("Demande validée annulée"), context=context)
    return result
