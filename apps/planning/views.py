"""Écrans du planning (docs/modules/06-planning.md) : vues semaine et mois, export.

Périmètre, filtres et exports sont vérifiés côté serveur (services.people_in_scope) : un
identifiant de service modifié dans l'URL ne montre jamais personne de plus."""

from datetime import date
from urllib.parse import urlencode

from django.http import HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET

from apps.core import permissions
from apps.core.access import module_is_enabled, module_required, permission_required
from apps.core.htmx import is_htmx
from apps.core.http import attachment
from apps.core.models import Module, Service, Site
from apps.core.ratelimit import (
    EXPORT_LIMIT_MESSAGE,
    export_allowed,
    export_limited_response,
    record_export,
)
from apps.planning import exports, services
from apps.planning.forms import FORMAT_LABELS, ExportForm, PlanningFilterForm

VIEWS = {"semaine", "mois"}


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _anchor(value, today):
    """Date demandée ; hors bornes (2000 à 2100) ou invalide : aujourd'hui (L4-18)."""
    try:
        day = date.fromisoformat(value) if value else today
    except ValueError:
        return today
    return day if services.in_bounds(day) else today


@require_GET
@module_required(Module.PLANNING)
@permission_required("planning.view")
def planning(request):
    me = request.employee
    today = timezone.localdate()
    view = request.GET.get("vue") if request.GET.get("vue") in VIEWS else "semaine"
    # Date de référence, gardée telle quelle : Semaine puis Mois puis Semaine revient à la
    # même semaine (la grille en déduit la période affichée).
    anchor = _anchor(request.GET.get("date"), today)
    company_wide = permissions.scope(me, "planning.view") == permissions.ALL
    q = request.GET.get("q", "").strip()
    service = _int(request.GET.get("service")) if company_wide else None
    site = _int(request.GET.get("site"))
    can_declare = module_is_enabled(request, Module.TELEWORK) and permissions.can(
        me, "requests.create"
    )
    grid = services.grid(
        me,
        view=view,
        anchor=anchor,
        filters=services.PeopleFilter(q=q, service=service, site=site),
        page=services.GridPage(request.GET.get("page"), can_declare),
        today=today,
    )
    base = reverse("planning:week")
    # « Exporter » reprend le service et la page affichés : le PDF se limite à cette page.
    export_params = {"page": grid.page_obj.number}
    if service:
        export_params["perimetre"] = service

    def link(**changes):
        params = {
            "vue": view,
            "date": anchor.isoformat(),
            "q": q,
            "service": service or "",
            "site": site or "",
        }
        params.update(changes)
        return f"{base}?{urlencode({k: v for k, v in params.items() if v})}"

    context = {
        "grid": grid,
        "view": view,
        "anchor": anchor,
        "title": services.period_title(view, grid.first, grid.last),
        "today": today,
        "query": q,
        "service": service,
        "site": site,
        "filter_form": PlanningFilterForm(
            request.GET,
            view=view,
            services_list=Service.objects.order_by("name") if company_wide else None,
            sites=Site.objects.order_by("name"),
        ),
        "company_wide": company_wide,
        "scope_label": _("Toute l'entreprise")
        if company_wide
        else (_("Service %(name)s") % {"name": me.service.name} if me.service_id else ""),
        "prev_url": link(date=services.shift(anchor, view, -1).isoformat()),
        "next_url": link(date=services.shift(anchor, view, 1).isoformat()),
        "today_url": link(date=today.isoformat()),
        "reset_url": f"{base}?{urlencode({'vue': view, 'date': anchor.isoformat()})}",
        "list_url": base,
        "filtered": bool(q or service or site),
        "can_declare": can_declare,
        "new_telework_url": reverse("approvals:new", args=["telework"]) if can_declare else "",
        "export_url": f"{reverse('planning:export')}?{urlencode(export_params)}",
        "can_see_closures": permissions.can(me, "closures.view"),
    }
    if is_htmx(request) and request.htmx.target == "planning-results":
        return render(request, "planning/planning.html#results", context)
    return render(request, "planning/planning.html", context)


@require_GET
@module_required(Module.PLANNING)
@permission_required("planning.export")
def export(request):
    me = request.employee
    today = timezone.localdate()
    submitted = "periode" in request.GET
    initial = {k: request.GET[k] for k in ("page", "perimetre") if request.GET.get(k)}
    form = ExportForm(request.GET if submitted else None, viewer=me, today=today, initial=initial)
    context = {"form": form, "planning_url": reverse("planning:week")}
    if submitted and form.is_valid() and not export_allowed(me):
        form.add_error(None, EXPORT_LIMIT_MESSAGE)
    if submitted and form.is_valid():
        first, last = form.cleaned_data["first"], form.cleaned_data["last"]
        people = form.cleaned_data["people"]
        if people is None:
            people = services.export_people(me, service=form.cleaned_data["perimetre"])[:6]
        _header, _lines, rows, working = services.export_rows(
            me, first, last, service=form.cleaned_data["perimetre"], people=people
        )
        context.update(
            {
                "preview_days": working[:5],
                "preview_rows": [
                    (row.employee, [c for c in row.cells if c.day in set(working[:5])])
                    for row in rows[:6]
                ],
                "more_days": len(working) > 5,
                "people_count": len(form.cleaned_data["people"])
                if form.cleaned_data["people"] is not None
                else services.export_people(me, service=form.cleaned_data["perimetre"]).count(),
                "days_count": len(working),
                "first": first,
                "last": last,
                "download_url": f"{reverse('planning:download')}?{request.GET.urlencode()}",
                "format_label": FORMAT_LABELS[form.cleaned_data["format"]],
            }
        )
    status = 422 if submitted and not form.is_valid() else 200
    if is_htmx(request) and request.htmx.target == "export-result":
        return render(request, "planning/export.html#result", context, status=status)
    return render(request, "planning/export.html", context, status=status)


@require_GET
@module_required(Module.PLANNING)
@permission_required("planning.export")
def download(request):
    me = request.employee
    form = ExportForm(request.GET, viewer=me, today=timezone.localdate())
    if not form.is_valid():
        return HttpResponse(status=400)
    if not record_export(me):
        return export_limited_response(request, reverse("planning:export"))
    first, last = form.cleaned_data["first"], form.cleaned_data["last"]
    fmt = form.cleaned_data["format"]
    content, content_type, filename = exports.build(
        me,
        first=first,
        last=last,
        service=form.cleaned_data["perimetre"],
        fmt=fmt,
        people=form.cleaned_data["people"],
    )
    exports.log_export(
        viewer=me,
        first=first,
        last=last,
        fmt_label=FORMAT_LABELS[fmt],
        scope_label=form.scope_label,
        request=request,
    )
    return attachment(content, content_type, filename)
