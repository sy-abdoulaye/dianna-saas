"""Règles métier des demandes (docs/modules/05-demandes.md) : quota, chevauchements,
conflits d'absence. Fonctions pures sur l'entreprise courante."""

from dataclasses import dataclass
from datetime import timedelta

from django.utils import timezone

from apps.approvals.models import (
    ACTIVE_STATUSES,
    LeaveRequest,
    OnCallDeclaration,
    RequestStatus,
    SummerCampaign,
    TeleworkRequest,
)
from apps.people.models import IN_POST_STATUSES, Employee


def monday_of(day):
    return day - timedelta(days=day.weekday())


def weekly_quota(employee: Employee) -> int:
    """La dérogation de la fiche remplace le quota de l'entreprise (L3-05)."""
    if employee.telework_days_override is not None:
        return employee.telework_days_override
    return employee.company.telework_max_per_week


def telework_days_in_week(employee: Employee, day, *, exclude_pk=None) -> int:
    """Jours en attente ou validés de la semaine du lundi au dimanche (L3-05)."""
    monday = monday_of(day)
    requests = TeleworkRequest.objects.filter(
        requester=employee,
        status__in=(RequestStatus.PENDING, RequestStatus.APPROVED),
        date__gte=monday,
        date__lte=monday + timedelta(days=6),
    )
    if exclude_pk:
        requests = requests.exclude(pk=exclude_pk)
    return requests.count()


def open_campaign():
    return SummerCampaign.objects.filter(status=SummerCampaign.Status.OPEN).first()


def leave_overlaps(employee: Employee, start, end, *, exclude_pk=None) -> bool:
    return (
        LeaveRequest.objects.filter(
            requester=employee, status__in=ACTIVE_STATUSES, start__lte=end, end__gte=start
        )
        .exclude(pk=exclude_pk)
        .exists()
    )


def on_call_overlaps(employee: Employee, start, end, *, exclude_pk=None) -> bool:
    """Deux astreintes actives de la même personne ne se chevauchent pas (L3-07)."""
    return (
        OnCallDeclaration.objects.filter(
            requester=employee,
            kind=OnCallDeclaration.Kind.ON_CALL,
            status__in=ACTIVE_STATUSES,
            start__lte=end,
            end__gte=start,
        )
        .exclude(pk=exclude_pk)
        .exists()
    )


@dataclass(frozen=True)
class Conflict:
    people: list
    service_size: int
    threshold: int

    @property
    def count(self) -> int:
        return len(self.people)

    @property
    def over_threshold(self) -> bool:
        """Plus de `threshold` % du service absent en même temps (demandeur compris)."""
        if not self.service_size:
            return False
        return (self.count + 1) * 100 > self.threshold * self.service_size


def conflicts_of(request: LeaveRequest) -> Conflict:
    """Autres personnes du même service avec une absence en attente ou validée sur la
    période (fiche demandes, M-03). L'envoi n'est jamais bloqué."""
    service_id = request.requester.service_id
    threshold = request.campaign.conflict_threshold if request.campaign else 30
    if service_id is None:
        return Conflict([], 0, threshold)
    others = (
        LeaveRequest.objects.filter(
            requester__service_id=service_id,
            status__in=ACTIVE_STATUSES,
            start__lte=request.end,
            end__gte=request.start,
        )
        .exclude(requester_id=request.requester_id)
        .select_related("requester")
    )
    people = sorted({leave.requester for leave in others}, key=lambda p: p.last_name)
    size = Employee.objects.filter(service_id=service_id, status__in=IN_POST_STATUSES).count()
    return Conflict(people, size, threshold)


def today():
    return timezone.localdate()
