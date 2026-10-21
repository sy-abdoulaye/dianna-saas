"""Tableau de bord (docs/modules/02-tableau-de-bord.md), complet au lot 4.

Seuls les blocs dont le module existe et est activé sont affichés (règle 6, L4-08) : les
indicateurs du matériel, des annonces, des justificatifs et des entretiens arrivent avec
leurs lots. Les compteurs « à traiter » sont ceux du menu (même fonction)."""

from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.translation import gettext as _
from django.utils.translation import ngettext

from apps.approvals import rules
from apps.approvals.kinds import KINDS, summary
from apps.approvals.models import LeaveRequest, RequestStatus, TeleworkRequest
from apps.approvals.views import is_validator, menu_counts
from apps.core import permissions
from apps.core.access import enabled_modules, module_is_enabled
from apps.core.models import AuditLog, Module, Service
from apps.people.models import IN_POST_STATUSES, Employee, EmployeeStatus, Role
from apps.planning import services as planning

NAV_TO_KIND = {"telework": "telework", "summer_leave": "leave", "on_call": "on_call"}


def _request_kinds(request):
    return [key for key, meta in KINDS.items() if module_is_enabled(request, meta.model.module)]


def _today_mix(request, me, today):
    """Répartition du jour dans le périmètre du planning (service, ou entreprise)."""
    if not module_is_enabled(request, Module.PLANNING):
        return None
    people = planning.people_in_scope(me)
    counts = planning.count_today(people, today, me)
    company_wide = permissions.scope(me, "planning.view") == permissions.ALL
    return {
        "counts": counts,
        "total": people.count(),
        "scope": _("entreprise")
        if company_wide
        else (me.service.name if me.service_id else _("mon équipe")),
    }


def indicators(request, me, today, todo_count, mix) -> list[tuple[str, object]]:
    kinds = _request_kinds(request)
    if me.role == Role.ADMIN:
        return [
            (
                _("Utilisateurs actifs"),
                Employee.objects.filter(status__in=IN_POST_STATUSES, user__is_active=True).count(),
            ),
            (_("Modules activés"), f"{len(enabled_modules(request))} / {len(Module.values)}"),
            (_("Services"), Service.objects.count()),
            (_("Événements du journal"), AuditLog.objects.count()),
        ]
    kpis = []
    if me.role == Role.HR:
        if kinds:
            kpis.append((_("Demandes à valider"), todo_count))
        if "leave" in kinds:
            campaign = rules.open_campaign()
            if campaign is not None:
                wishes = campaign.requests.exclude(
                    status__in=(RequestStatus.CANCELLED, RequestStatus.REFUSED)
                ).count()
                kpis.append((_("Vœux de la campagne"), wishes))
        kpis += [
            (_("Effectif en poste"), Employee.objects.filter(status=EmployeeStatus.ACTIVE).count()),
            (
                _("Arrivées à venir"),
                Employee.objects.filter(status=EmployeeStatus.UPCOMING).count(),
            ),
        ]
        return kpis
    if is_validator(me):
        if kinds:
            kpis.append((_("Demandes à valider"), todo_count))
        if mix:
            counts = mix["counts"]
            kpis.append((_("Équipe sur site aujourd'hui"), f"{counts['site']} / {mix['total']}"))
            kpis.append((_("En télétravail aujourd'hui"), counts["tt"]))
            kpis.append((_("En congés aujourd'hui"), counts["cp"]))
        return kpis
    if "telework" in kinds:
        monday, sunday = planning.week_of(today)
        used = TeleworkRequest.objects.filter(
            requester=me,
            status__in=(RequestStatus.PENDING, RequestStatus.APPROVED),
            date__range=(monday, sunday),
        ).count()
        kpis.append((_("Télétravail cette semaine"), f"{used} / {rules.weekly_quota(me)}"))
    if kinds:
        pending = sum(
            KINDS[key].model.objects.filter(requester=me, status=RequestStatus.PENDING).count()
            for key in kinds
        )
        kpis.append((_("Mes demandes en attente"), pending))
    if "leave" in kinds:
        upcoming = (
            LeaveRequest.objects.filter(requester=me, status=RequestStatus.APPROVED, end__gte=today)
            .order_by("start")
            .first()
        )
        kpis.append(
            (_("Mes prochains congés"), date_format(upcoming.start, "j F") if upcoming else "—")
        )
    if mix:
        kpis.append((_("Sur site aujourd'hui"), f"{mix['counts']['site']} / {mix['total']}"))
    return kpis


def todo_items(request, me) -> list[dict]:
    """Une ligne par module avec des demandes à valider (mêmes compteurs que le menu)."""
    if not is_validator(me):
        return []
    items = []
    for nav_key, count in menu_counts(request).items():
        if not count:
            continue
        meta = KINDS[NAV_TO_KIND[nav_key]]
        items.append(
            {
                "icon": meta.icon,
                "text": ngettext(
                    "%(n)s demande de %(kind)s à valider",
                    "%(n)s demandes de %(kind)s à valider",
                    count,
                )
                % {"n": count, "kind": meta.lower},
                "url": f"{reverse(meta.url_name)}?onglet=a-valider",
            }
        )
    return items


def latest_requests(request, me) -> list:
    rows = []
    for key in _request_kinds(request):
        meta = KINDS[key]
        for obj in meta.model.objects.filter(requester=me).order_by("-submitted_at")[:4]:
            obj.kind_meta = meta
            obj.summary = summary(obj)
            rows.append(obj)
    return sorted(rows, key=lambda r: r.submitted_at, reverse=True)[:4]


def home(request):
    me = request.employee
    today = timezone.localdate()
    todo = todo_items(request, me)
    todo_count = sum(menu_counts(request).values()) if is_validator(me) else 0
    mix = _today_mix(request, me, today)
    can_declare = (
        me.role != Role.ADMIN
        and module_is_enabled(request, Module.TELEWORK)
        and permissions.can(me, "requests.create")
    )
    context = {
        "today": today,
        "kpis": indicators(request, me, today, todo_count, mix),
        "is_admin": me.role == Role.ADMIN,
        "todo": todo,
        "mix": mix,
        "planning_url": reverse("planning:week") if mix else "",
        "latest": latest_requests(request, me) if me.role != Role.ADMIN else None,
        "has_requests": bool(_request_kinds(request)),
        "new_telework_url": reverse("approvals:new", args=["telework"]) if can_declare else "",
    }
    return render(request, "dashboard/home.html", context)
