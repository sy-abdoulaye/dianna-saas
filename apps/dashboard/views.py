"""Tableau de bord, version initiale (lot 2, docs/modules/02-tableau-de-bord.md).

Seuls les blocs dont les données existent sont affichés : les indicateurs liés aux demandes,
au matériel, aux annonces et aux entretiens arrivent avec leurs modules (règle 6)."""

from django.shortcuts import render
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.core.access import enabled_modules
from apps.core.models import AuditLog, Module, Service
from apps.people.models import IN_POST_STATUSES, Employee, EmployeeStatus, Role


def indicators(request) -> list[tuple[str, object]]:
    employee = request.employee
    if employee.role == Role.ADMIN:
        return [
            (
                _("Utilisateurs actifs"),
                Employee.objects.filter(status__in=IN_POST_STATUSES, user__is_active=True).count(),
            ),
            (_("Modules activés"), f"{len(enabled_modules(request))} / {len(Module.values)}"),
            (_("Services"), Service.objects.count()),
            (_("Événements du journal"), AuditLog.objects.count()),
        ]
    if employee.role == Role.HR:
        return [
            (_("Effectif en poste"), Employee.objects.filter(status=EmployeeStatus.ACTIVE).count()),
            (
                _("Arrivées à venir"),
                Employee.objects.filter(status=EmployeeStatus.UPCOMING).count(),
            ),
        ]
    return []


def home(request):
    context = {
        "today": timezone.localdate(),
        "kpis": indicators(request),
        "is_admin": request.employee.role == Role.ADMIN,
    }
    return render(request, "dashboard/home.html", context)
