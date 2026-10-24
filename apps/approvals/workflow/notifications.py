"""Notifications des valideurs et du demandeur, avec l'e-mail différé de 45 s (M-16).

Les fonctions du paquet s'appellent par la façade `workflow` (apps/approvals/workflow/
__init__.py) : point d'entrée unique, et point de remplacement des tests."""

from django.urls import reverse
from django.utils.translation import gettext as _

from apps.approvals import workflow
from apps.approvals.kinds import kind_of, summary
from apps.approvals.models import (
    RequestStatus,
)
from apps.core import notifications
from apps.core.models import Notification
from apps.people.models import Employee


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
    created = notifications.notify_many(
        validators,
        text,
        workflow._module_url(request, kind.todo_tab),
        Notification.Kind.REQUEST,
        email_subject=_("Demande à valider : %(kind)s") % {"kind": kind.lower},
        source=request,
    )
    return [notification.pk for notification in created]


def _notify_requester(request, verb: str, reason: str = "", *, email: bool = True) -> int:
    kind = kind_of(request)
    text = _("Votre demande (%(kind)s, %(summary)s) a été %(verb)s.") % {
        "kind": kind.lower,
        "summary": summary(request),
        "verb": verb,
    }
    if reason:
        text = f"{text} {_('Motif :')} {reason}"
    return workflow._notify(
        request.requester,
        text,
        workflow._module_url(request),
        Notification.Kind.DECISION,
        email_subject=_("Votre demande de %(kind)s a été %(verb)s")
        % {"kind": kind.lower, "verb": verb}
        if email
        else "",
        request=request,
    )


def _current_validators(request) -> list[Employee]:
    if request.status == RequestStatus.MANAGER_APPROVED:
        return workflow.hr_validators(request.requester)
    if request.status == RequestStatus.PENDING:
        return workflow.first_validators(request)
    return []
