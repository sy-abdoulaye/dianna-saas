"""Description de chaque type de demande : libellés du prototype, icône, résumé."""

from dataclasses import dataclass
from datetime import timedelta

from django.utils.translation import gettext_lazy as _

from apps.approvals.models import LeaveRequest, OnCallDeclaration, TeleworkRequest, TransportProof
from apps.core.dates import format_date


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
    todo_tab: str = "a-valider"  # onglet « À valider » de l'écran du module


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
    "transport": Kind(
        "transport",
        TransportProof,
        _("Justificatifs de transport"),
        _("justificatif de transport"),
        _("Abonnements de transport en commun, validés par les RH"),
        _("Ajouter un justificatif"),
        "ticket",
        _("Justificatif"),
        "approvals:transport",
    ),
}


def register_kind(kind: Kind) -> Kind:
    """Types de demande d'autres applications (matériel, L5-04)."""
    KINDS[kind.key] = kind
    return kind


def kind_of(request) -> Kind:
    return KINDS[request.request_type]


def full_date(day) -> str:
    return format_date(day, "full")


def short_date(day) -> str:
    return format_date(day, "short")


def span(start, end) -> str:
    if start == end:
        return format_date(start, "long")
    if start.year == end.year:
        return _("du %(a)s au %(b)s") % {
            "a": format_date(start, "day_month"),
            "b": format_date(end, "long"),
        }
    return _("du %(a)s au %(b)s") % {
        "a": format_date(start, "long"),
        "b": format_date(end, "long"),
    }


def workdays(start, end) -> int:
    count, day = 0, start
    while day <= end:
        if day.weekday() < 5:
            count += 1
        day += timedelta(days=1)
    return count


def euros(amount) -> str:
    return f"{amount:.2f}".replace(".", ",") + "\u00a0€"


SUMMARIES = {}  # type de demande → fonction de résumé (autres applications)


def summary(request) -> str:
    """Résumé d'une ligne (tableaux, notifications, e-mails)."""
    if request.request_type in SUMMARIES:
        return SUMMARIES[request.request_type](request)
    if isinstance(request, TransportProof):
        # Ordre du prototype : mois · type · montant · nom du fichier.
        parts = [
            format_date(request.month, "month"),
            request.get_ticket_type_display(),
            euros(request.amount),
        ]
        return " · ".join([*parts, request.original_name] if request.original_name else parts)
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
