"""Lectures de la page d'un type de demande : onglets visibles et lignes filtrées. Les vues
restent minces ; les règles de périmètre restent celles de `permissions` et de `workflow`."""

from django.db.models import Q, QuerySet
from django.utils.translation import gettext as _

from apps.approvals import workflow
from apps.approvals.kinds import summary
from apps.approvals.models import RequestStatus
from apps.core import permissions

TAB_MINE, TAB_TODO, TAB_TEAM = "mes-demandes", "a-valider", "equipe"


def is_validator(employee) -> bool:
    return employee.has_reports or workflow.is_hr_or_admin(employee)


def request_tabs(me, model) -> tuple[list[tuple[str, str, int]], QuerySet]:
    """Onglets (clé, libellé, compteur) et demandes « À valider ». Types validés par les RH
    (transport) : ni « À valider » ni « Mon équipe » pour un manager, qui ne voit pas les
    justificatifs de son équipe (docs/04-permissions.md)."""
    tabs = [(TAB_MINE, _("Mes demandes"), 0)]
    validator = workflow.is_hr_or_admin(me) if model.hr_validated else is_validator(me)
    todo = workflow.to_validate(me, model) if validator else model.objects.none()
    if validator:
        tabs.append((TAB_TODO, _("À valider"), todo.count()))
    if workflow.is_hr_or_admin(me):
        tabs.append((TAB_TEAM, _("Toutes les demandes"), 0))
    elif me.has_reports and permissions.scope(me, model.view_action) != permissions.SELF:
        tabs.append((TAB_TEAM, _("Mon équipe"), 0))
    return tabs, todo


def request_rows(me, model, tab: str, todo: QuerySet, *, q: str, status: str) -> QuerySet:
    if tab == TAB_MINE:
        rows = model.objects.filter(requester=me)
    elif tab == TAB_TODO:
        rows = todo
    else:
        rows = permissions.scope_queryset(me, model.objects.all(), model.view_action).exclude(
            requester=me
        )
    rows = rows.select_related("requester", "requester__service", "requester__manager")
    if q and tab == TAB_MINE:
        # « Rechercher dans mes demandes » : dans le résumé affiché (dates, type, montant),
        # comme le prototype. Les demandes d'une personne sont peu nombreuses.
        needle = q.casefold()
        rows = rows.filter(pk__in=[row.pk for row in rows if needle in summary(row).casefold()])
    elif q:
        rows = rows.filter(
            Q(requester__first_name__icontains=q) | Q(requester__last_name__icontains=q)
        )
    if status in RequestStatus.values:
        rows = rows.filter(status=status)
    return rows.order_by("-submitted_at", "-pk")
