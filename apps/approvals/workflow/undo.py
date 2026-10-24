"""Annulation immédiate d'une transition par son auteur (30 s, A3-01).

Les fonctions du paquet s'appellent par la façade `workflow` (apps/approvals/workflow/
__init__.py) : point d'entrée unique, et point de remplacement des tests."""

from django.db import transaction
from django.utils.translation import gettext as _

from apps.agenda.models import CalendarEvent
from apps.approvals import workflow
from apps.approvals.models import (
    ACTIVE_STATUSES,
    LeaveRequest,
    RequestEvent,
    RequestStatus,
)
from apps.core import notifications
from apps.core.context import ActionContext
from apps.core.models import Notification

REACTIVATING = ("refuse", "cancel", "cancel_approved")


UNDO_EXPECTED_STATUS = {
    "approve": (RequestStatus.APPROVED, RequestStatus.MANAGER_APPROVED),
    "refuse": (RequestStatus.REFUSED,),
    "cancel": (RequestStatus.CANCELLED,),
    "cancel_approved": (RequestStatus.CANCELLED,),
}


@transaction.atomic
def undo(model, payload: dict, *, context: ActionContext):
    """Défait la dernière transition de son auteur, seulement si l'événement qu'elle a créé
    est toujours le dernier de la demande : sinon « Une autre décision a été prise depuis »
    et rien n'est modifié (A3-01). Après un envoi : la demande, son événement et ses
    notifications sont supprimés ; le journal garde « demande envoyée puis retirée » (L1-08).
    Après une décision : l'état précédent est rétabli ; si la demande redevient active
    (refus ou annulation défaits), les contrôles métier sont refaits sous verrou (A3-02)."""
    actor, http_request = context.person(), context.request
    request = workflow._lock_for_undo(model, payload)
    if payload["action"] == "submit":
        workflow._undo_submit(request, actor, http_request=http_request)
        return None
    return workflow._undo_decision(request, payload, actor, http_request=http_request)


def _lock_for_undo(model, payload: dict):
    """Verrouille la demande (et la fiche du demandeur si elle redevient active) et vérifie
    que l'événement à défaire est toujours le dernier."""
    found = model.objects.filter(public_id=payload["id"]).values_list("requester_id").first()
    if found is None:
        raise workflow.WorkflowError(workflow.ALREADY_PROCESSED)
    if payload["action"] in workflow.REACTIVATING:
        workflow._lock_requester(found[0])
    request = (
        model.objects.select_for_update(of=("self",))
        .select_related("requester", "requester__manager", "requester__company")
        .filter(public_id=payload["id"])
        .first()
    )
    if request is None:
        raise workflow.WorkflowError(workflow.ALREADY_PROCESSED)
    if payload.get("event") is None or workflow._latest_event_id(request) != payload["event"]:
        raise workflow.WorkflowError(workflow.OTHER_DECISION)
    return request


def _undo_submit(request, actor, *, http_request) -> None:
    if request.requester_id != actor.pk:
        raise workflow.WorkflowError(workflow.ALREADY_PROCESSED)
    Notification.objects.filter(source_type=request.request_type, source_id=request.pk).delete()
    CalendarEvent.objects.filter(source_type=request.request_type, source_id=request.pk).delete()
    RequestEvent.objects.filter(request_type=request.request_type, request_id=request.pk).delete()
    workflow._audit(
        request, actor, "withdrawn", _("Demande envoyée puis retirée"), http_request=http_request
    )
    request.delete()
    if request.file_field:
        # Justificatif retiré dans les 30 s : supprimé une fois l'annulation validée (L5-05).
        transaction.on_commit(lambda: workflow._forget_file(request))


def _undo_decision(request, payload: dict, actor, *, http_request):
    action, previous = payload["action"], payload["previous"]
    if (
        request.status not in workflow.UNDO_EXPECTED_STATUS[action]
        or previous not in ACTIVE_STATUSES
    ):
        raise workflow.WorkflowError(workflow.ALREADY_PROCESSED)
    workflow._restore_previous_state(request, action, payload)
    if action in workflow.REACTIVATING:
        errors = workflow.check_request(request, campaign=getattr(request, "campaign", None))
        if errors:
            raise workflow.WorkflowError(next(iter(errors.values())))
    try:
        workflow._save_checked(request)
    except workflow.RequestValidationError as error:
        raise workflow.WorkflowError(error.message) from error
    Notification.objects.filter(
        pk__in=payload.get("notifications", []),
        source_type=request.request_type,
        source_id=request.pk,
    ).delete()
    notifications.retract_unsent(request)
    workflow._event(request, actor, RequestEvent.Action.REVERTED)
    workflow.sync_calendar(request)
    # La transition défaite avait retiré « Demande à valider » : les valideurs actuels sont
    # de nouveau prévenus.
    if request.status != RequestStatus.APPROVED:
        workflow._notify_validators(request, workflow._current_validators(request))
    workflow._audit(request, actor, "reverted", _("Décision annulée"), http_request=http_request)
    return request


def _restore_previous_state(request, action: str, payload: dict) -> None:
    previous = payload["previous"]
    request.status = previous
    if action == "cancel_approved":
        request.decision_comment = payload.get("comment", "")
    elif action in ("approve", "refuse"):
        request.decided_by, request.decided_at, request.decision_comment = None, None, ""
        if previous == RequestStatus.PENDING and isinstance(request, LeaveRequest):
            request.manager_decided_by, request.manager_decided_at = None, None
