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
- enregistre un RequestEvent, met à jour l'événement de calendrier, crée les notifications,
  met en file les e-mails (45 s, annulables) et écrit le journal d'audit.
Les annulations immédiates (« Annuler » dans la notification visuelle, 30 s) défont la
dernière transition de leur auteur.
"""

from dataclasses import dataclass, field

from django.db import transaction
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.agenda.models import CalendarEvent
from apps.approvals.kinds import kind_of, summary
from apps.approvals.models import (
    LeaveRequest,
    RequestEvent,
    RequestStatus,
    TeleworkRequest,
)
from apps.core import audit, notifications, permissions
from apps.core.hosts import company_url
from apps.core.mail import queue_undoable_email
from apps.core.models import Notification
from apps.people.models import IN_POST_STATUSES, Employee, Role

AUTO_APPROVAL_NO_VALIDATOR = "validation automatique : aucun valideur disponible"
AUTO_APPROVAL_TELEWORK = "validation automatique dans la limite du quota (M-02)"


class WorkflowError(Exception):
    def __init__(self, message):
        super().__init__(str(message))
        self.message = message


ALREADY_PROCESSED = _("Cette demande a déjà été traitée.")


@dataclass
class TransitionResult:
    """Ce qu'il faut pour annuler immédiatement la transition (jeton signé de 30 s)."""

    request: object
    previous_status: str = ""
    previous_comment: str = ""
    notification_ids: list = field(default_factory=list)
    auto_approved: bool = False

    def undo_payload(self, action: str) -> dict:
        return {
            "action": action,
            "type": self.request.request_type,
            "id": str(self.request.public_id),
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
    autres que le demandeur (M-12, L3-02)."""
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
    if request.status != RequestStatus.PENDING:
        return None
    manager = active_manager(request.requester)
    if manager is not None and manager.pk != employee.pk and is_hr_or_admin(employee):
        return manager
    return None


def to_validate(employee, model):
    """Onglet « À valider » : équipe directe pour un manager ; pour les RH et administrateurs,
    seulement les personnes sans manager (M-12) et l'étape RH des congés d'été."""
    from django.db.models import Q

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


def _event(request, actor, action, comment=""):
    RequestEvent.objects.create(
        request_type=request.request_type,
        request_id=request.pk,
        actor=actor,
        action=action,
        comment=comment,
    )


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
    notification = notifications.notify(recipient, text, url=url, kind=kind)
    if email_subject and recipient.user_id and recipient.user.is_active:
        body = render_to_string(
            "approvals/email/notification.txt",
            {
                "recipient": recipient,
                "text": text,
                "url": company_url(recipient.company, url),
            },
        )
        queue_undoable_email(email_subject, body, [recipient.user.email], notification=notification)
    return notification.pk


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
            _module_url(request, "a-valider"),
            Notification.Kind.REQUEST,
            email_subject=_("Demande à valider : %(kind)s") % {"kind": kind.lower},
        )
        for v in validators
    ]


def _notify_requester(request, verb: str, reason: str = "") -> int:
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
        % {"kind": kind.lower, "verb": verb},
    )


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


@transaction.atomic
def submit(model, requester: Employee, data: dict, *, http_request=None) -> TransitionResult:
    """Envoi. La fiche du demandeur est verrouillée : deux envois simultanés ne peuvent pas
    dépasser le quota ni créer deux demandes le même jour. Les contrôles métier sont refaits
    par le formulaire dans la même transaction (voir forms.py)."""
    request = model(requester=requester, submitted_at=timezone.now(), **data)
    request.save()
    _event(request, requester, RequestEvent.Action.SUBMITTED)
    result = TransitionResult(request, previous_status="")

    validators = first_validators(request)
    company = requester.company
    if not validators:
        _approve_automatically(request, AUTO_APPROVAL_NO_VALIDATOR, http_request)
        result.auto_approved = True
    elif isinstance(request, TeleworkRequest) and company.telework_auto_approve:
        _approve_automatically(request, AUTO_APPROVAL_TELEWORK, http_request)
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
    _event(request, None, RequestEvent.Action.AUTO_APPROVED, reason)
    sync_calendar(request)
    _audit(
        request,
        None,
        "auto_approved",
        _("Demande validée"),
        http_request=http_request,
        extra=reason,
    )


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
        _event(request, actor, RequestEvent.Action.MANAGER_APPROVED, comment)
        sync_calendar(request)
        result.notification_ids = [_notify_requester(request, _("validée par votre manager"))]
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
    _event(request, actor, RequestEvent.Action.APPROVED, comment)
    sync_calendar(request)
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
    _event(request, actor, RequestEvent.Action.REFUSED, reason)
    sync_calendar(request)
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
    _event(request, actor, RequestEvent.Action.CANCELLED)
    sync_calendar(request)
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
    _event(request, actor, RequestEvent.Action.CANCELLED, reason)
    sync_calendar(request)
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


@transaction.atomic
def undo(model, payload: dict, actor: Employee, *, http_request=None):
    """Défait la dernière transition de son auteur. Après un envoi : la demande, son
    événement et ses notifications sont supprimés ; le journal garde « demande envoyée puis
    retirée » (L1-08). Après une décision : l'état précédent est rétabli."""
    request = model.objects.select_for_update().filter(public_id=payload["id"]).first()
    if request is None:
        raise WorkflowError(ALREADY_PROCESSED)
    Notification.objects.filter(pk__in=payload.get("notifications", [])).delete()
    if payload["action"] == "submit":
        if request.requester_id != actor.pk or request.status not in (
            RequestStatus.PENDING,
            RequestStatus.APPROVED,
        ):
            raise WorkflowError(ALREADY_PROCESSED)
        if (
            request.status == RequestStatus.APPROVED
            and not RequestEvent.objects.filter(
                request_type=request.request_type,
                request_id=request.pk,
                action=RequestEvent.Action.AUTO_APPROVED,
            ).exists()
        ):
            raise WorkflowError(ALREADY_PROCESSED)
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
        return None
    previous = payload["previous"]
    expected = {
        "approve": (RequestStatus.APPROVED, RequestStatus.MANAGER_APPROVED),
        "refuse": (RequestStatus.REFUSED,),
        "cancel": (RequestStatus.CANCELLED,),
        "cancel_approved": (RequestStatus.CANCELLED,),
    }[payload["action"]]
    if request.status not in expected:
        raise WorkflowError(ALREADY_PROCESSED)
    request.status = previous
    if payload["action"] == "cancel_approved":
        request.decision_comment = payload.get("comment", "")
    elif payload["action"] in ("approve", "refuse"):
        request.decided_by, request.decided_at, request.decision_comment = None, None, ""
        if previous == RequestStatus.PENDING and isinstance(request, LeaveRequest):
            request.manager_decided_by, request.manager_decided_at = None, None
    request.save()
    _event(request, actor, RequestEvent.Action.REVERTED)
    sync_calendar(request)
    _audit(request, actor, "reverted", _("Décision annulée"), http_request=http_request)
    return request


def history(request):
    return RequestEvent.objects.filter(
        request_type=request.request_type, request_id=request.pk
    ).select_related("actor")
