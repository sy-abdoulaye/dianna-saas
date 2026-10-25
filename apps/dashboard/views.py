"""Tableau de bord (docs/modules/02-tableau-de-bord.md).

Seuls les blocs dont le module existe et est activé sont affichés (règle 6, L4-08). Les
compteurs « à traiter » sont ceux du menu et des listes (mêmes fonctions) : demandes à
valider, entretiens à compléter (lot 7), comptes rendus à valider ou à envoyer (lot 7)."""

from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import ngettext

from apps.approvals import rules
from apps.approvals.kinds import KINDS, summary
from apps.approvals.models import LeaveRequest, RequestStatus, TeleworkRequest
from apps.approvals.views import is_validator, menu_counts
from apps.careers import selectors as careers
from apps.core import permissions
from apps.core.access import enabled_modules, module_is_enabled
from apps.core.dates import format_date
from apps.core.models import AuditLog, Module, Service
from apps.interventions import selectors as reports
from apps.interventions.models import EDITABLE_STATUSES, InterventionReport
from apps.people.models import IN_POST_STATUSES, Employee, EmployeeStatus, Role
from apps.planning import services as planning

NAV_TO_KIND = {
    "telework": "telework",
    "summer_leave": "leave",
    "on_call": "on_call",
    "transport": "transport",
    "equipment": "equipment",
}


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
    """Quatre indicateurs au plus, propres au profil (fiche 02)."""
    kinds = _request_kinds(request)
    if me.role == Role.ADMIN:
        return _admin_indicators(request)
    if me.role == Role.HR:
        return _hr_indicators(request, kinds, todo_count)
    if is_validator(me):
        return _manager_indicators(request, me, kinds, todo_count, mix)
    return _employee_indicators(request, me, today, kinds, mix)


def _admin_indicators(request) -> list[tuple[str, object]]:
    return [
        (
            _("Utilisateurs actifs"),
            Employee.objects.filter(status__in=IN_POST_STATUSES, user__is_active=True).count(),
        ),
        (_("Modules activés"), f"{len(enabled_modules(request))} / {len(Module.values)}"),
        (_("Services"), Service.objects.count()),
        (_("Événements du journal"), AuditLog.objects.count()),
    ]


def _hr_indicators(request, kinds, todo_count) -> list[tuple[str, object]]:
    kpis = []
    counts = menu_counts(request)
    if "transport" in kinds:
        kpis.append((_("Justificatifs à valider"), counts.get("transport", 0)))
    if any(k != "transport" for k in kinds):
        kpis.append((_("Demandes à valider"), todo_count - counts.get("transport", 0)))
    review_campaign = (
        careers.current_campaign() if module_is_enabled(request, Module.CAREERS) else None
    )
    if review_campaign is not None:
        progress = careers.campaign_progress(request.employee, review_campaign)
        kpis.append((_("Campagne d'entretiens"), f"{progress} %"))
    campaign = rules.open_campaign() if "leave" in kinds else None
    if campaign is not None:
        wishes = campaign.requests.exclude(
            status__in=(RequestStatus.CANCELLED, RequestStatus.REFUSED)
        ).count()
        kpis.append((_("Vœux de la campagne"), wishes))
    return [
        *kpis,
        (_("Effectif en poste"), Employee.objects.filter(status=EmployeeStatus.ACTIVE).count()),
        (_("Arrivées à venir"), Employee.objects.filter(status=EmployeeStatus.UPCOMING).count()),
    ]


def _manager_indicators(request, me, kinds, todo_count, mix) -> list[tuple[str, object]]:
    """Fiche 02 : demandes à valider, équipe sur site, entretiens à mener (lot 7),
    télétravail aujourd'hui ; « En congés aujourd'hui » quand la carrière est désactivée."""
    kpis = [(_("Demandes à valider"), todo_count)] if kinds else []
    if mix:
        kpis.append((_("Équipe sur site aujourd'hui"), f"{mix['counts']['site']} / {mix['total']}"))
    if module_is_enabled(request, Module.CAREERS):
        kpis.append((_("Entretiens à mener"), len(careers.todo_reviews(me))))
    if mix:
        kpis.append((_("En télétravail aujourd'hui"), mix["counts"]["tt"]))
        if not module_is_enabled(request, Module.CAREERS):
            kpis.append((_("En congés aujourd'hui"), mix["counts"]["cp"]))
    return kpis


def _employee_indicators(request, me, today, kinds, mix) -> list[tuple[str, object]]:
    kpis = []
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
    if module_is_enabled(request, Module.EQUIPMENT):
        from apps.equipment.models import EquipmentItem

        held = EquipmentItem.objects.filter(holder=me).exclude(status=EquipmentItem.Status.RETIRED)
        kpis.append((_("Matériel attribué"), held.count()))
    if module_is_enabled(request, Module.ANNOUNCEMENTS):
        from apps.announcements import selectors as announcements

        kpis.append((_("Annonces non lues"), announcements.unread_count(me)))
    if "leave" in kinds and len(kpis) < 4:
        upcoming = (
            LeaveRequest.objects.filter(requester=me, status=RequestStatus.APPROVED, end__gte=today)
            .order_by("start")
            .first()
        )
        next_leave = format_date(upcoming.start, "day_month") if upcoming else "—"
        kpis.append((_("Mes prochains congés"), next_leave))
    if mix and len(kpis) < 4:
        kpis.append((_("Sur site aujourd'hui"), f"{mix['counts']['site']} / {mix['total']}"))
    return kpis


def todo_items(request, me) -> list[dict]:
    """« À traiter » : demandes à valider par module, entretiens à compléter, comptes rendus
    à valider ou à envoyer ; chaque ligne mène à l'écran où l'action se fait."""
    return [*_request_todo(request, me), *_career_todo(request, me), *_report_todo(request, me)]


def _line(icon: str, text: str, url: str) -> dict:
    return {"icon": icon, "text": text, "url": url}


def _career_todo(request, me) -> list[dict]:
    if not module_is_enabled(request, Module.CAREERS):
        return []
    count = len(careers.todo_reviews(me))
    if not count:
        return []
    text = ngettext("%(n)s entretien à compléter", "%(n)s entretiens à compléter", count) % {
        "n": count
    }
    return [_line("up", text, f"{reverse('careers:home')}?avancement=a-faire")]


def _report_todo(request, me) -> list[dict]:
    if not module_is_enabled(request, Module.INTERVENTIONS):
        return []
    lines = []
    url = reverse("interventions:list")
    own = InterventionReport.objects.filter(employee=me, status__in=EDITABLE_STATUSES).count()
    if own:
        text = ngettext(
            "%(n)s compte rendu à envoyer ou compléter",
            "%(n)s comptes rendus à envoyer ou compléter",
            own,
        ) % {"n": own}
        lines.append(_line("tool", text, url))
    waiting = reports.to_validate(me).count() if permissions.can(me, "interventions.decide") else 0
    if waiting:
        text = ngettext(
            "%(n)s compte rendu à valider", "%(n)s comptes rendus à valider", waiting
        ) % {"n": waiting}
        lines.append(_line("tool", text, f"{url}?onglet=a-valider"))
    return lines


def _request_todo(request, me) -> list[dict]:
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
                "url": f"{reverse(meta.url_name)}?onglet={meta.todo_tab}",
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


def _latest_announcements(request, me) -> list | None:
    """Bloc « Annonces » : les 3 dernières, épinglées en premier (prototype)."""
    if not module_is_enabled(request, Module.ANNOUNCEMENTS):
        return None
    from apps.announcements import selectors as announcements

    return announcements.latest(me)


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
        "announcements": _latest_announcements(request, me),
        "equipment_url": reverse("equipment:home")
        if module_is_enabled(request, Module.EQUIPMENT)
        else "",
        "careers_url": reverse("careers:home")
        if module_is_enabled(request, Module.CAREERS)
        else "",
        "new_telework_url": reverse("approvals:new", args=["telework"]) if can_declare else "",
    }
    return render(request, "dashboard/home.html", context)
