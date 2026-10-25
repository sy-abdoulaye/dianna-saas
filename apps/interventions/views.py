"""Écrans du suivi d'intervention (`/interventions/`, docs/modules/11-interventions.md).

Le formulaire est une page complète : ajouter ou retirer un bloc ne recharge jamais la page
(apps/core/repeatable.py), et le brouillon s'enregistre automatiquement toutes les 30 s
quand la saisie a changé (ui.js). Chaque enregistrement porte la version lue : depuis une
version dépassée (autre onglet), rien n'est écrasé."""

import json

from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from apps.approvals import workflow
from apps.core import permissions, repeatable, undo
from apps.core.access import module_is_enabled, module_required
from apps.core.context import ActionContext
from apps.core.dates import day_stamp, format_date
from apps.core.htmx import (
    PAGE_CHANGED,
    Toast,
    after_action,
    confirm_response,
    error_response,
    form_error_response,
    is_htmx,
    modal_form_response,
)
from apps.core.models import Module
from apps.core.pdf import pdf_response
from apps.interventions import forms, selectors, services
from apps.interventions.models import InterventionReport, ReportItem

CHANGED = "reportsChanged"
PER_PAGE = 8
TAB_MINE, TAB_TODO, TAB_ALL = "mes-comptes-rendus", "a-valider", "equipe"
FORM = "interventions/form.html"
module_view = module_required(Module.INTERVENTIONS)


def _visible(request, public_id) -> InterventionReport:
    return get_object_or_404(selectors.visible_reports(request.employee), public_id=public_id)


def _own(request, public_id) -> InterventionReport:
    return get_object_or_404(
        InterventionReport.objects.select_related("mission", "employee"),
        public_id=public_id,
        employee=request.employee,
    )


def menu_count(request) -> dict:
    """Compteur du menu, identique à l'onglet « À valider »."""
    me = getattr(request, "employee", None)
    if me is None or not module_is_enabled(request, Module.INTERVENTIONS):
        return {}
    if not permissions.can(me, "interventions.decide"):
        return {}
    return {"interventions": selectors.to_validate(me).count()}


# ---------- Liste ----------


def _tabs(me) -> list[tuple[str, str, int]]:
    tabs = [(TAB_MINE, _("Mes comptes rendus"), 0)]
    sees_all = workflow.is_hr_or_admin(me)
    if me.has_reports or sees_all:
        tabs.append((TAB_TODO, _("À valider"), selectors.to_validate(me).count()))
        tabs.append((TAB_ALL, _("Tous les comptes rendus") if sees_all else _("Mon équipe"), 0))
    return tabs


def _rows(me, tab: str, request):
    if tab == TAB_TODO:
        reports = selectors.to_validate(me)
    elif tab == TAB_ALL:
        reports = selectors.visible_reports(me).exclude(employee=me)
    else:
        reports = selectors.visible_reports(me).filter(employee=me)
    q = request.GET.get("q", "").strip()
    period = forms.parse_month(request.GET.get("periode", ""))
    status = request.GET.get("statut", "")
    rows = selectors.filter_reports(reports, q=q, period=period, status=status)
    return rows, bool(q or period or status)


@require_GET
@module_view
def report_list(request):
    me = request.employee
    tabs = _tabs(me)
    tab = request.GET.get("onglet", TAB_MINE)
    if tab not in {key for key, _label, _n in tabs}:
        tab = TAB_MINE
    rows, filtered = _rows(me, tab, request)
    page_obj = Paginator(rows, PER_PAGE).get_page(request.GET.get("page"))
    for row in page_obj.object_list:
        row.editable = row.employee_id == me.pk and row.is_editable
        row.can_decide = selectors.can_decide(me, row)
        row.percent = round(row.average or 0)
    url = reverse("interventions:list")
    context = {
        "tab": tab,
        "tabs": [
            {"label": label, "url": f"{url}?onglet={key}", "count": n, "active": key == tab}
            for key, label, n in tabs
        ],
        "page_obj": page_obj,
        "filtered": filtered,
        "show_who": tab != TAB_MINE,
        "filter_form": forms.ReportFilterForm(request.GET, tab=tab, mine=tab == TAB_MINE),
        "list_url": url,
    }
    if is_htmx(request) and request.htmx.target == "results":
        return render(request, "interventions/list.html#results", context)
    return render(request, "interventions/list.html", context)


# ---------- Formulaire ----------


def _form_context(request, form, done, next_items, report=None) -> dict:
    me = request.employee
    manager = workflow.active_manager(me)
    return {
        "form": form,
        "done": done,
        "next": next_items,
        "report": report,
        "missions": selectors.missions_of(me),
        "recipient": manager.full_name if manager else _("Équipe RH"),
        "done_block": repeatable.BLOCKS["interventions-done"],
        "next_block": repeatable.BLOCKS["interventions-next"],
        "save_url": reverse("interventions:save"),
        "extension_options": [(forms.NO, _("Non"), ""), (forms.YES, _("Oui"), "")],
        "cancel_url": reverse("interventions:detail", args=[report.public_id])
        if report
        else reverse("interventions:list"),
    }


@require_GET
@module_view
def new(request):
    last = selectors.last_report(request.employee)
    form = forms.ReportForm(initial=forms.report_initial(last=last))
    done, next_items = forms.formsets()
    return render(request, FORM, _form_context(request, form, done, next_items))


@require_GET
@module_view
def edit(request, public_id):
    report = _own(request, public_id)
    if not report.is_editable:
        return render(request, "interventions/locked.html", {"report": report})
    form = forms.ReportForm(initial=forms.report_initial(report=report))
    done, next_items = forms.formsets(report=report)
    return render(request, FORM, _form_context(request, form, done, next_items, report))


def _report_of(request, form) -> InterventionReport | None:
    public_id = form.cleaned_data.get("report")
    if not public_id:
        return None
    return _own(request, public_id)


@require_POST
@module_view
def save(request):
    """Enregistrer le brouillon, envoyer, ou l'enregistrement automatique (`act`)."""
    act = request.POST.get("act", "draft")
    send = act == "send"
    form = forms.ReportForm(request.POST, send=send)
    done, next_items = forms.formsets(request.POST, send=send)
    valid = form.is_valid() and done.is_valid() and next_items.is_valid()
    if act == "autosave":
        return _autosave(request, form, done, next_items, valid)
    if not valid:
        return form_error_response(request, FORM, _form_context(request, form, done, next_items))
    report = _report_of(request, form)
    context = ActionContext.of(request)
    try:
        report = services.save_report(
            report,
            forms.report_data(form, done, next_items),
            version=form.cleaned_data.get("version"),
            context=context,
        )
        transition = (
            services.submit(report, version=report.version, context=context) if send else None
        )
    except services.ReportError as error:
        form.add_error(error.field if error.field in form.fields else None, error.message)
        context_ = _form_context(request, form, done, next_items, report)
        return form_error_response(request, FORM, context_)
    if transition is not None:
        return _sent(request, transition)
    toast = Toast(
        title=_("Brouillon enregistré"),
        message=_("Vous pourrez le compléter plus tard."),
        action_label=_("Voir le compte rendu"),
        action_url=services.report_url(report),
    )
    return after_action(request, toast, go_to=reverse("interventions:list"), page_form=True)


def _autosave(request, form, done, next_items, valid):
    """Enregistrement automatique : met à jour la mention « Enregistré à … », la version et
    l'identifiant du brouillon ; jamais d'écrasement depuis une version dépassée."""
    if not valid:
        return render(request, "interventions/partials/autosave.html", {"pending": True})
    try:
        report = services.save_report(
            _report_of(request, form),
            forms.report_data(form, done, next_items),
            version=form.cleaned_data.get("version"),
            context=ActionContext.of(request),
        )
    except services.ReportError as error:
        return error_response(error)
    response = render(
        request,
        "interventions/partials/autosave.html",
        {"report": report, "saved_at": format_date(timezone.now(), "time")},
    )
    response["HX-Replace-Url"] = reverse("interventions:edit", args=[report.public_id])
    return response


# ---------- Transitions ----------


def _undo_token(request, transition) -> str:
    token = undo.make_token(request, "interventions.undo", json.dumps(transition.undo_payload()))
    return reverse("interventions:undo", args=[token])


def _sent(request, transition):
    recipients = selectors.validators(transition.report)
    names = ", ".join(person.full_name for person in recipients[:3])
    toast = Toast(
        title=_("Compte rendu envoyé"),
        message=_("%(names)s a reçu une notification dans Dianna.") % {"names": names},
        emphasis=names,
        undo_url=_undo_token(request, transition),
    )
    return after_action(
        request,
        toast,
        go_to=reverse("interventions:detail", args=[transition.report.public_id]),
        close_modal=True,
    )


def _undo(request, payload) -> Toast:
    services.undo(json.loads(payload.target), context=ActionContext.of(request))
    return Toast(
        title=_("Action annulée"), message=_("Le compte rendu a repris son état."), kind="info"
    )


undo.register("interventions.undo", _undo, refresh=PAGE_CHANGED)


@require_http_methods(["GET", "POST"])
@module_view
def send(request, public_id):
    report = _own(request, public_id)
    manager = workflow.active_manager(report.employee)
    if request.method == "GET":
        return confirm_response(
            request,
            title=_("Envoyer le compte rendu ?"),
            text=_(
                "Il sera transmis à %(name)s. Vous ne pourrez plus le modifier, sauf si un "
                "complément vous est demandé."
            )
            % {"name": manager.full_name if manager else _("l'équipe RH")},
            ok_label=_("Envoyer"),
            ok_icon="send",
            action_url=reverse("interventions:send", args=[report.public_id]),
        )
    try:
        transition = services.submit(report, context=ActionContext.of(request))
    except services.ReportError as error:
        return error_response(error, close_modal=True)
    return _sent(request, transition)


@require_http_methods(["GET", "POST"])
@module_view
def decide(request, public_id, approve):
    report = _visible(request, public_id)
    form = forms.DecisionForm(request.POST or None, approve=approve)
    name = "approve" if approve else "request_changes"
    context = {
        "form": form,
        "report": report,
        "approve": approve,
        "replaced": selectors.replaced_manager(request.employee, report),
        "action_url": reverse(f"interventions:{name}", args=[report.public_id]),
    }
    if request.method == "POST" and form.is_valid():
        try:
            transition = services.decide(
                report,
                approve=approve,
                note=form.cleaned_data["note"],
                context=ActionContext.of(request),
            )
        except services.ReportError as error:
            if error.field == "note":
                form.add_error("note", error.message)
                return form_error_response(
                    request, "interventions/partials/decide_modal.html", context
                )
            return error_response(error, close_modal=True, refresh=PAGE_CHANGED)
        title = _("Compte rendu validé") if approve else _("Complément demandé")
        employee = transition.report.employee.full_name
        toast = Toast(
            title=title,
            message=_("%(name)s a reçu une notification dans Dianna.") % {"name": employee},
            emphasis=employee,
            undo_url=_undo_token(request, transition),
        )
        return after_action(request, toast, refresh=PAGE_CHANGED, close_modal=True)
    return modal_form_response(request, "interventions/partials/decide_modal.html", context)


# ---------- Détail et export ----------


def _detail_context(request, report: InterventionReport) -> dict:
    me = request.employee
    items = list(report.items.all())
    today = timezone.localdate()
    for item in items:
        item.late = selectors.is_late(item, today)
    return {
        "report": report,
        "done_items": [i for i in items if i.section == ReportItem.Section.DONE],
        "next_items": [i for i in items if i.section == ReportItem.Section.NEXT],
        "average": selectors.average_completion(report),
        "events": report.events.select_related("actor"),
        "editable": report.employee_id == me.pk and report.is_editable,
        "can_decide": selectors.can_decide(me, report),
        "replaced": selectors.replaced_manager(me, report)
        if selectors.can_decide(me, report)
        else None,
        "validator": workflow.active_manager(report.employee),
        "company": request.company,
    }


@require_GET
@module_view
def detail(request, public_id):
    report = _visible(request, public_id)
    return render(request, "interventions/detail.html", _detail_context(request, report))


@require_GET
@module_view
def report_pdf(request, public_id):
    report = _visible(request, public_id)
    response = pdf_response(
        request,
        "interventions/pdf.html",
        _detail_context(request, report),
        filename=f"compte-rendu-{day_stamp(timezone.localdate())}.pdf",
        back_url=services.report_url(report),
    )
    if response.status_code == 200:
        services.log_export(report, context=ActionContext.of(request))
    return response
