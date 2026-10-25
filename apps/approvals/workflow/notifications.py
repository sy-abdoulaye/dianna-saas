"""Notifications des valideurs et du demandeur, avec l'e-mail différé de 45 s (M-16).

Les modules du paquet s'importent directement entre eux ; le reste de l'application passe
par la façade `workflow` (apps/approvals/workflow/__init__.py)."""

from django.urls import reverse
from django.utils.translation import gettext as _

from apps.approvals.kinds import kind_of, summary
from apps.approvals.models import (
    ApprovalRequest,
    RequestStatus,
)
from apps.approvals.workflow.validators import first_validators, hr_validators
from apps.core import notifications
from apps.core.models import Notification
from apps.people.models import Employee


def module_url(request: ApprovalRequest, tab: str = "") -> str:
    url = reverse(kind_of(request).url_name)
    return f"{url}?onglet={tab}" if tab else url


def _notify(
    recipient: Employee,
    text: str,
    url: str,
    kind: str,
    *,
    email_subject: str = "",
    request: ApprovalRequest | None = None,
) -> int:
    return notifications.notify(
        recipient, text, url=url, kind=kind, email_subject=email_subject, source=request
    ).pk


def _notify_validators(request: ApprovalRequest, validators: list[Employee]) -> list[int]:
    kind = kind_of(request)
    text = _("%(name)s : %(kind)s à valider (%(summary)s)") % {
        "name": request.requester.full_name,
        "kind": kind.lower,
        "summary": summary(request),
    }
    created = notifications.notify_many(
        validators,
        text,
        module_url(request, kind.todo_tab),
        Notification.Kind.REQUEST,
        email_subject=_("Demande à valider : %(kind)s") % {"kind": kind.lower},
        source=request,
    )
    return [notification.pk for notification in created]


def _notify_requester(
    request: ApprovalRequest, verb: str, reason: str = "", *, email: bool = True
) -> int:
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
        module_url(request),
        Notification.Kind.DECISION,
        email_subject=_("Votre demande de %(kind)s a été %(verb)s")
        % {"kind": kind.lower, "verb": verb}
        if email
        else "",
        request=request,
    )


def _current_validators(request: ApprovalRequest) -> list[Employee]:
    if request.status == RequestStatus.MANAGER_APPROVED:
        return hr_validators(request.requester)
    if request.status == RequestStatus.PENDING:
        return first_validators(request)
    return []
