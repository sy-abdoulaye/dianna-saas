"""Lectures du suivi d'intervention : périmètre, « À valider », filtres, suggestions.

Valideur (M-11, M-12) : le manager direct en poste ; sans lui, les RH et administrateurs
autres que l'auteur. Les RH et administrateurs peuvent valider tout compte rendu à la place du
manager (bandeau, journal) ; leur onglet « À valider » ne montre que les personnes sans
manager.
"""

from datetime import date

from django.db.models import Avg, Q, QuerySet
from django.utils import timezone

from apps.approvals import workflow
from apps.core import permissions
from apps.interventions.models import (
    InterventionReport,
    Mission,
    ReportItem,
    ReportStatus,
)
from apps.people.models import IN_POST_STATUSES, Employee


def visible_reports(viewer: Employee) -> QuerySet[InterventionReport]:
    reports = InterventionReport.objects.select_related("employee", "employee__manager", "mission")
    return permissions.scope_queryset(viewer, reports, "interventions.view")


def validators(report: InterventionReport) -> list[Employee]:
    manager = workflow.active_manager(report.employee)
    if manager is not None:
        return [manager]
    return workflow.hr_validators(exclude=report.employee)


def can_decide(actor: Employee, report: InterventionReport) -> bool:
    if report.status != ReportStatus.SUBMITTED or actor.pk == report.employee_id:
        return False
    manager = workflow.active_manager(report.employee)
    if manager is not None and manager.pk == actor.pk:
        return True
    return workflow.is_hr_or_admin(actor) and permissions.can(actor, "interventions.decide", report)


def replaced_manager(actor: Employee, report: InterventionReport) -> Employee | None:
    """Manager présent remplacé par un RH ou un administrateur (bandeau et journal, M-12)."""
    manager = workflow.active_manager(report.employee)
    if manager is None or manager.pk == actor.pk:
        return None
    return manager


def to_validate(viewer: Employee) -> QuerySet[InterventionReport]:
    """Onglet « À valider » et compteur du menu : équipe directe pour un manager ; pour les
    RH et administrateurs, seulement les personnes sans manager en poste."""
    submitted = visible_reports(viewer).filter(status=ReportStatus.SUBMITTED)
    submitted = submitted.exclude(employee=viewer)
    managed = Q(employee__manager=viewer, employee__manager__status__in=IN_POST_STATUSES)
    if workflow.is_hr_or_admin(viewer):
        without_manager = Q(employee__manager__isnull=True) | ~Q(
            employee__manager__status__in=IN_POST_STATUSES
        )
        return submitted.filter(managed | without_manager)
    return submitted.filter(managed)


def filter_reports(
    reports: QuerySet[InterventionReport], *, q: str, period: date | None, status: str
) -> QuerySet[InterventionReport]:
    if q:
        reports = reports.filter(
            Q(mission__name__icontains=q)
            | Q(employee__first_name__icontains=q)
            | Q(employee__last_name__icontains=q)
        )
    if period is not None:
        reports = reports.filter(period=period)
    if status in ReportStatus.values:
        reports = reports.filter(status=status)
    return reports.annotate(
        average=Avg("items__completion", filter=Q(items__section=ReportItem.Section.DONE))
    ).order_by("-period", "-pk")


def average_completion(report: InterventionReport) -> int:
    value = report.items.filter(section=ReportItem.Section.DONE).aggregate(
        average=Avg("completion")
    )["average"]
    return round(value or 0)


def missions_of(employee: Employee) -> list[str]:
    """Suggestions du champ « Intervention » : les interventions déjà citées par la personne
    seulement (jamais celles des autres)."""
    names = Mission.objects.filter(reports__employee=employee).values_list("name", flat=True)
    return sorted(set(names))


def last_report(employee: Employee) -> InterventionReport | None:
    return (
        InterventionReport.objects.filter(employee=employee)
        .select_related("mission")
        .order_by("-period", "-pk")
        .first()
    )


def month_choices(today: date | None = None) -> list[date]:
    """Périodes proposées : les 12 derniers mois et le mois suivant (Q10)."""
    today = today or timezone.localdate()
    first = today.replace(day=1)
    months = []
    for offset in range(-12, 2):
        index = first.month - 1 + offset
        months.append(date(first.year + index // 12, index % 12 + 1, 1))
    return sorted(months, reverse=True)


def is_late(item: ReportItem, today: date | None = None) -> bool:
    """Repère « Délai dépassé » : délai passé et réalisation inférieure à 100 %."""
    today = today or timezone.localdate()
    return bool(item.due_date and item.due_date < today and (item.completion or 0) < 100)
