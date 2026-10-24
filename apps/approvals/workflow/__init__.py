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

Façade du moteur des demandes : les applications et les tests importent `workflow` et ses
noms publics d'ici ; le code est réparti dans les modules du paquet."""

from apps.approvals.workflow.campaigns import (
    CAMPAIGN_FIELDS,
    _campaign_audit,
    close_summer_campaign,
    create_summer_campaign,
    open_summer_campaign,
)
from apps.approvals.workflow.checks import (
    SUBSCRIPTIONS,
    _check_leave,
    _check_on_call,
    _check_summer_campaign,
    _check_telework,
    _check_transport,
    check_request,
)
from apps.approvals.workflow.common import (
    ALREADY_PROCESSED,
    AMOUNT_RANGE,
    AUTO_APPROVAL_NO_VALIDATOR,
    AUTO_APPROVAL_TELEWORK,
    CAMPAIGN_ALREADY_OPEN,
    OTHER_DECISION,
    SAME_DAY,
    UNKNOWN_CONSTRAINT,
    RequestValidationError,
    TransitionResult,
    WorkflowError,
    _audit,
    _event,
    _forget_file,
    _latest_event_id,
    _lock,
    _lock_requester,
    _save_checked,
    _write_file,
    history,
    sync_calendar,
)
from apps.approvals.workflow.notifications import (
    _current_validators,
    _module_url,
    _notify,
    _notify_requester,
    _notify_validators,
)
from apps.approvals.workflow.transitions import (
    _approve_automatically,
    _submit,
    _substitution,
    approve,
    cancel,
    cancel_approved,
    refuse,
    submit,
)
from apps.approvals.workflow.undo import (
    REACTIVATING,
    UNDO_EXPECTED_STATUS,
    _lock_for_undo,
    _restore_previous_state,
    _undo_decision,
    _undo_submit,
    undo,
)
from apps.approvals.workflow.validators import (
    acting_for,
    active_manager,
    can_cancel_approved,
    can_decide,
    first_validators,
    has_hr_step,
    hr_validators,
    is_hr_or_admin,
    to_validate,
)
from apps.core.constraints import CONSTRAINT_MESSAGES, INVALID_VALUE, constraint_name

__all__ = [
    "ALREADY_PROCESSED",
    "AMOUNT_RANGE",
    "AUTO_APPROVAL_NO_VALIDATOR",
    "AUTO_APPROVAL_TELEWORK",
    "CAMPAIGN_ALREADY_OPEN",
    "CAMPAIGN_FIELDS",
    "CONSTRAINT_MESSAGES",
    "INVALID_VALUE",
    "OTHER_DECISION",
    "REACTIVATING",
    "SAME_DAY",
    "SUBSCRIPTIONS",
    "UNDO_EXPECTED_STATUS",
    "UNKNOWN_CONSTRAINT",
    "RequestValidationError",
    "TransitionResult",
    "WorkflowError",
    "_approve_automatically",
    "_audit",
    "_campaign_audit",
    "_check_leave",
    "_check_on_call",
    "_check_summer_campaign",
    "_check_telework",
    "_check_transport",
    "_current_validators",
    "_event",
    "_forget_file",
    "_latest_event_id",
    "_lock",
    "_lock_for_undo",
    "_lock_requester",
    "_module_url",
    "_notify",
    "_notify_requester",
    "_notify_validators",
    "_restore_previous_state",
    "_save_checked",
    "_submit",
    "_substitution",
    "_undo_decision",
    "_undo_submit",
    "_write_file",
    "acting_for",
    "active_manager",
    "approve",
    "can_cancel_approved",
    "can_decide",
    "cancel",
    "cancel_approved",
    "check_request",
    "close_summer_campaign",
    "constraint_name",
    "create_summer_campaign",
    "first_validators",
    "has_hr_step",
    "history",
    "hr_validators",
    "is_hr_or_admin",
    "open_summer_campaign",
    "refuse",
    "submit",
    "sync_calendar",
    "to_validate",
    "undo",
]
