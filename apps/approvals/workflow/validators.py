"""Qui valide une demande, qui peut décider ou annuler, et ce qui attend chaque valideur.

Les fonctions du paquet s'appellent par la façade `workflow` (apps/approvals/workflow/
__init__.py) : point d'entrée unique, et point de remplacement des tests."""

from apps.approvals.models import (
    LeaveRequest,
    RequestStatus,
)
from apps.core import permissions
from apps.people.models import IN_POST_STATUSES, Employee, Role


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
    autres que le demandeur (M-12, L3-02). Types validés par les RH (transport, matériel,
    L5-04) : les RH et administrateurs autres que le demandeur."""
    if request.hr_validated:
        return hr_validators(exclude=request.requester)
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
    if request.hr_validated:
        return (
            request.status == RequestStatus.PENDING
            and is_hr_or_admin(employee)
            and permissions.can(employee, request.decide_action, request)
        )
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
    if request.status != RequestStatus.PENDING or request.hr_validated:
        return None
    manager = active_manager(request.requester)
    if manager is not None and manager.pk != employee.pk and is_hr_or_admin(employee):
        return manager
    return None


def to_validate(employee, model):
    """Onglet « À valider » : équipe directe pour un manager ; pour les RH et administrateurs,
    seulement les personnes sans manager (M-12) et l'étape RH des congés d'été."""
    from django.db.models import Q

    related = ("requester", "requester__service", "requester__manager")
    if model.hr_validated:
        # Transport, matériel : toutes les demandes en attente, pour les RH seulement.
        if not is_hr_or_admin(employee):
            return model.objects.none()
        return (
            model.objects.filter(status=RequestStatus.PENDING)
            .exclude(requester=employee)
            .select_related(*related)
        )
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
