"""Description de chaque type de demande : libellés du prototype, icône, résumé."""

from dataclasses import dataclass
from datetime import timedelta

from django.utils.formats import date_format
from django.utils.translation import gettext_lazy as _

from apps.approvals.models import LeaveRequest, OnCallDeclaration, TeleworkRequest


@dataclass(frozen=True)
class Kind:
    key: str
    model: type
    label: str
    lower: str
    subtitle: str
    new_label: str
    icon: str
    column: str
    url_name: str


KINDS = {
    "telework": Kind(
        "telework",
        TeleworkRequest,
        _("Télétravail"),
        _("télétravail"),
        _("Jours de télétravail déclarés et validés par le manager"),
        _("Déclarer un jour de télétravail"),
        "home",
        _("Jour"),
        "approvals:telework",
    ),
    "leave": Kind(
        "leave",
        LeaveRequest,
        _("Congés estivaux"),
        _("congés"),
        _("Vœux de congés d'été et autres absences, arbitrés par le manager"),
        _("Déposer un vœu de congés"),
        "sun",
        _("Période"),
        "approvals:leave",
    ),
    "on_call": Kind(
        "on_call",
        OnCallDeclaration,
        _("Astreintes"),
        _("astreinte"),
        _("Astreintes et interventions déclarées, validées par le manager"),
        _("Déclarer une astreinte"),
        "clock",
        _("Astreinte"),
        "approvals:on_call",
    ),
}


def kind_of(request) -> Kind:
    return KINDS[request.request_type]


def full_date(day) -> str:
    return date_format(day, "l j F Y")


def short_date(day) -> str:
    return date_format(day, "j M")


def span(start, end) -> str:
    if start == end:
        return date_format(start, "j F Y")
    if start.year == end.year:
        return _("du %(a)s au %(b)s") % {
            "a": date_format(start, "j F"),
            "b": date_format(end, "j F Y"),
        }
    return _("du %(a)s au %(b)s") % {
        "a": date_format(start, "j F Y"),
        "b": date_format(end, "j F Y"),
    }


def workdays(start, end) -> int:
    count, day = 0, start
    while day <= end:
        if day.weekday() < 5:
            count += 1
        day += timedelta(days=1)
    return count


def summary(request) -> str:
    """Résumé d'une ligne (tableaux, notifications, e-mails)."""
    if isinstance(request, TeleworkRequest):
        return full_date(request.date)
    if isinstance(request, LeaveRequest):
        days = workdays(request.start, request.end)
        text = _("%(span)s · %(n)s j ouvrés") % {
            "span": span(request.start, request.end),
            "n": days,
        }
        if request.leave_type == LeaveRequest.LeaveType.OTHER:
            text = f"{request.get_leave_type_display()} · {text}"
        return text
    text = f"{request.get_kind_display()} · {span(request.start, request.end)}"
    if request.hours:
        text += " · " + str(request.hours).replace(".", ",").removesuffix(",0") + " h"
    return text
