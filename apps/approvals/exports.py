"""Exports RH des demandes (L3-08) : réservés aux RH et administrateurs (`requests.export`).

- Récapitulatif mensuel du télétravail validé, par salarié (CSV, Excel).
- Export paie des astreintes et interventions validées du mois, par salarié (CSV, Excel).
- Synthèse par service d'une campagne de congés d'été : vœux, absents par semaine, alertes de
  dépassement du seuil (écran, CSV, Excel).

Chaque export est inscrit au journal d'audit avec la période et le format, sans nom de
personne (CLAUDE.md, règle 5)."""

import calendar
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Count, Q
from django.utils.formats import date_format
from django.utils.translation import gettext as _

from apps.approvals.models import (
    ACTIVE_STATUSES,
    LeaveRequest,
    OnCallDeclaration,
    RequestStatus,
    TeleworkRequest,
)
from apps.core import audit, permissions
from apps.core.csv_export import csv_content
from apps.core.models import Service
from apps.core.xlsx_export import XLSX_CONTENT_TYPE, Styled, xlsx_content
from apps.people.models import IN_POST_STATUSES, Employee

CSV_CONTENT_TYPE = "text/csv; charset=utf-8"
FORMAT_LABELS = {"csv": "CSV", "xlsx": "Excel"}


class ExportDeniedError(Exception):
    pass


def _check(viewer):
    if not permissions.can(viewer, "requests.export"):
        raise ExportDeniedError


def month_bounds(month: date) -> tuple[date, date]:
    first = month.replace(day=1)
    return first, first.replace(day=calendar.monthrange(first.year, first.month)[1])


def month_label(month: date) -> str:
    return date_format(month, "F Y")


def _file(fmt, title, header, rows, stem):
    if fmt == "xlsx":
        return xlsx_content(title, header, rows), XLSX_CONTENT_TYPE, f"{stem}.xlsx"
    return csv_content(header, rows), CSV_CONTENT_TYPE, f"{stem}.csv"


def _log(viewer, what, period, fmt, request):
    audit.log(
        "requests.exported",
        _("%(what)s, %(period)s, %(fmt)s")
        % {"what": what, "period": period, "fmt": FORMAT_LABELS[fmt]},
        actor=viewer,
        request=request,
    )


def _people_ids(viewer):
    """Périmètre de l'export : celui de `requests.export` (toute l'entreprise pour les RH)."""
    return permissions.scope_queryset(viewer, Employee.objects.all(), "requests.view").values("pk")


# ---------- Télétravail ----------


def telework_month(viewer, month: date, fmt: str, *, request=None):
    _check(viewer)
    first, last = month_bounds(month)
    validated = TeleworkRequest.objects.filter(
        status=RequestStatus.APPROVED, date__range=(first, last), requester__in=_people_ids(viewer)
    ).values_list("requester_id", "date")
    by_person: dict[int, list[date]] = {}
    for person_id, day in validated:
        by_person.setdefault(person_id, []).append(day)
    people = (
        Employee.objects.filter(pk__in=_people_ids(viewer))
        .filter(_in_post_or(by_person))
        .select_related("service")
        .order_by("last_name", "first_name")
    )
    header = [
        _("Collaborateur"),
        _("Matricule"),
        _("Service"),
        _("Jours de télétravail validés"),
        _("Dates"),
    ]
    rows = [
        [
            person.full_name,
            person.registration_number,
            person.service.name if person.service else "",
            len(by_person.get(person.pk, [])),
            ", ".join(date_format(d, "d/m") for d in sorted(by_person.get(person.pk, []))),
        ]
        for person in people
    ]
    _log(viewer, _("Récapitulatif du télétravail"), month_label(month), fmt, request)
    return _file(fmt, _("Télétravail"), header, rows, f"teletravail-{first:%Y-%m}")


def _in_post_or(by_person):
    return Q(status__in=IN_POST_STATUSES) | Q(pk__in=list(by_person))


# ---------- Astreintes (paie) ----------


def on_call_month(viewer, month: date, fmt: str, *, request=None):
    _check(viewer)
    first, last = month_bounds(month)
    declarations = OnCallDeclaration.objects.filter(
        status=RequestStatus.APPROVED,
        start__lte=last,
        end__gte=first,
        requester__in=_people_ids(viewer),
    ).select_related("requester", "requester__service")
    totals: dict[int, dict] = {}
    for item in declarations:
        person = totals.setdefault(
            item.requester_id,
            {"person": item.requester, "days": 0, "count": 0, "hours": Decimal("0")},
        )
        if item.kind == OnCallDeclaration.Kind.ON_CALL:
            person["days"] += (min(item.end, last) - max(item.start, first)).days + 1
        elif first <= item.start <= last:
            person["count"] += 1
            person["hours"] += item.hours or Decimal("0")
    header = [
        _("Collaborateur"),
        _("Matricule"),
        _("Service"),
        _("Jours d'astreinte"),
        _("Interventions"),
        _("Heures d'intervention"),
    ]
    rows = [
        [
            t["person"].full_name,
            t["person"].registration_number,
            t["person"].service.name if t["person"].service else "",
            t["days"],
            t["count"],
            str(t["hours"]).replace(".", ","),
        ]
        for t in sorted(
            totals.values(), key=lambda t: (t["person"].last_name, t["person"].first_name)
        )
    ]
    _log(viewer, _("Export paie des astreintes"), month_label(month), fmt, request)
    return _file(fmt, _("Astreintes"), header, rows, f"astreintes-{first:%Y-%m}")


# ---------- Synthèse de campagne ----------


@dataclass
class ServiceSummary:
    service: object
    size: int
    wishes: int = 0
    weeks: list = field(default_factory=list)  # [(lundi, absents, pourcentage, alerte)]


def campaign_summary(campaign) -> tuple[list[date], list[ServiceSummary]]:
    """Par service : nombre de vœux (en attente ou validés) et absents par semaine de la
    période ; alerte quand les absents dépassent le seuil de la campagne (L3-15)."""
    monday = campaign.period_start - timedelta(days=campaign.period_start.weekday())
    mondays = []
    while monday <= campaign.period_end:
        mondays.append(monday)
        monday += timedelta(days=7)
    leaves = LeaveRequest.objects.filter(campaign=campaign, status__in=ACTIVE_STATUSES).values_list(
        "requester_id", "requester__service_id", "start", "end"
    )
    sizes = dict(
        Employee.objects.filter(status__in=IN_POST_STATUSES, service__isnull=False)
        .values_list("service_id")
        .annotate(n=Count("pk"))
    )
    absent: dict[tuple[int, date], set] = {}
    wishes: dict[int, int] = {}
    for person_id, service_id, start, end in leaves:
        if service_id is None:
            continue
        wishes[service_id] = wishes.get(service_id, 0) + 1
        for week in mondays:
            week_end = week + timedelta(days=4)
            if start <= week_end and end >= week:
                absent.setdefault((service_id, week), set()).add(person_id)
    summaries = []
    for service in Service.objects.order_by("name"):
        size = sizes.get(service.pk, 0)
        summary = ServiceSummary(service, size, wishes.get(service.pk, 0))
        for week in mondays:
            count = len(absent.get((service.pk, week), set()))
            percent = round(count * 100 / size) if size else 0
            summary.weeks.append(
                (
                    week,
                    count,
                    percent,
                    bool(size) and count * 100 > campaign.conflict_threshold * size,
                )
            )
        summaries.append(summary)
    return mondays, summaries


def campaign_file(viewer, campaign, fmt: str, *, request=None):
    _check(viewer)
    mondays, summaries = campaign_summary(campaign)
    header = [_("Service"), _("Effectif"), _("Vœux")] + [
        _("Semaine du %(day)s") % {"day": date_format(m, "d/m")} for m in mondays
    ]
    rows = []
    for item in summaries:
        line = [item.service.name, item.size, item.wishes]
        for _week, count, percent, alert in item.weeks:
            text = f"{count} ({percent} %)"
            line.append(
                Styled(text, "err-bg", "err-ink")
                if alert and fmt == "xlsx"
                else (f"{text} !" if alert else text)
            )
        rows.append(line)
    _log(
        viewer,
        _("Synthèse de la campagne %(label)s") % {"label": campaign.label},
        _("période de la campagne"),
        fmt,
        request,
    )
    return _file(fmt, _("Synthèse"), header, rows, f"synthese-{campaign.pk}")
