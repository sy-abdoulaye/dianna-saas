"""Écrans du matériel (`/materiel/`, docs/modules/07-materiel.md).

Onglets : Mon matériel (tous), Mon équipe (manager), Parc, Demandes et Signalements (RH et
administrateurs). Chaque action vérifie la permission côté serveur ; un salarié reçoit 403
sur les adresses du parc. Les demandes de matériel passent par le moteur commun
(apps/approvals) : valider, refuser, annuler et l'historique sont les siens."""

import json

from django.core.paginator import Paginator
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from apps.approvals import workflow
from apps.approvals.kinds import summary
from apps.approvals.models import RequestStatus
from apps.core import permissions, undo
from apps.core.access import module_required, permission_required, require
from apps.core.context import ActionContext
from apps.core.htmx import (
    Toast,
    after_action,
    confirm_response,
    error_response,
    form_error_response,
)
from apps.core.models import Module
from apps.equipment import services
from apps.equipment.forms import (
    AssignForm,
    CloseIssueForm,
    IssueForm,
    ItemForm,
    StockChoiceForm,
)
from apps.equipment.models import (
    EquipmentIssue,
    EquipmentItem,
    EquipmentKind,
    EquipmentRequest,
)

CHANGED = "equipmentChanged"
PER_PAGE = 8
TAB_MINE, TAB_TEAM, TAB_PARK, TAB_REQUESTS, TAB_ISSUES = (
    "mon-materiel",
    "equipe",
    "parc",
    "demandes",
    "signalements",
)


def _tabs(me):
    tabs = [(TAB_MINE, _("Mon matériel"), 0)]
    if me.has_reports and not workflow.is_hr_or_admin(me):
        tabs.append((TAB_TEAM, _("Mon équipe"), 0))
    if permissions.can(me, "equipment.manage"):
        tabs.append((TAB_PARK, _("Parc"), 0))
    if permissions.can(me, "equipment.decide"):
        pending = workflow.to_validate(me, EquipmentRequest).count()
        tabs.append((TAB_REQUESTS, _("Demandes"), pending))
    if permissions.can(me, "equipment.manage"):
        open_issues = EquipmentIssue.objects.filter(status=EquipmentIssue.Status.OPEN).count()
        tabs.append((TAB_ISSUES, _("Signalements"), open_issues))
    return tabs


def _decorate_requests(rows, me):
    for row in rows:
        row.summary = summary(row)
        row.can_decide = workflow.can_decide(me, row)
        row.can_cancel = row.requester_id == me.pk and row.is_open
        row.needs_item = (
            row.status == RequestStatus.APPROVED
            and permissions.can(me, "equipment.manage")
            and not row.assignments.exists()
        )
    return rows


@require_GET
@module_required(Module.EQUIPMENT)
def home(request):
    me = request.employee
    tabs = _tabs(me)
    tab = request.GET.get("onglet", TAB_MINE)
    if tab not in {key for key, _label, _n in tabs}:
        tab = TAB_MINE
    url = reverse("equipment:home")
    context = {
        "tab": tab,
        "tabs": [
            {"label": label, "url": f"{url}?onglet={key}", "count": count, "active": key == tab}
            for key, label, count in tabs
        ],
        "can_manage": permissions.can(me, "equipment.manage"),
        "new_request_url": reverse("approvals:new", args=["equipment"]),
        "kinds": EquipmentKind.choices,
        "statuses": EquipmentItem.Status.choices,
    }
    if tab == TAB_MINE:
        context["items"] = (
            EquipmentItem.objects.filter(holder=me)
            .exclude(status=EquipmentItem.Status.RETIRED)
            .select_related("holder")
        )
        context["my_requests"] = _decorate_requests(
            list(EquipmentRequest.objects.filter(requester=me).prefetch_related("assignments")),
            me,
        )
    elif tab == TAB_TEAM:
        team = permissions.scope_queryset(me, EquipmentItem.objects.all(), "equipment.view")
        context["items"] = (
            team.exclude(holder=me).exclude(holder__isnull=True).select_related("holder")
        )
    elif tab == TAB_PARK:
        context.update(_park(request))
    elif tab == TAB_REQUESTS:
        todo = list(workflow.to_validate(me, EquipmentRequest).prefetch_related("assignments"))
        done = (
            EquipmentRequest.objects.exclude(status=RequestStatus.PENDING)
            .select_related("requester")
            .prefetch_related("assignments")[:30]
        )
        context["todo"] = _decorate_requests(todo, me)
        context["done"] = _decorate_requests(list(done), me)
    else:
        context["open_issues"] = EquipmentIssue.objects.filter(
            status=EquipmentIssue.Status.OPEN
        ).select_related("item", "reported_by", "item__holder")
        context["closed_issues"] = EquipmentIssue.objects.filter(
            status=EquipmentIssue.Status.CLOSED
        ).select_related("item", "reported_by", "closed_by")[:30]
    return render(request, "equipment/home.html", context)


def _park(request) -> dict:
    items = EquipmentItem.objects.select_related("holder")
    q = request.GET.get("q", "").strip()
    kind = request.GET.get("type", "")
    status = request.GET.get("etat", "")
    if q:
        items = items.filter(
            Q(model__icontains=q)
            | Q(serial_number__icontains=q)
            | Q(holder__first_name__icontains=q)
            | Q(holder__last_name__icontains=q)
        )
    if kind in EquipmentKind.values:
        items = items.filter(kind=kind)
    if status in EquipmentItem.Status.values:
        items = items.filter(status=status)
    else:
        items = items.exclude(status=EquipmentItem.Status.RETIRED)  # masqués par défaut
    page_obj = Paginator(items, PER_PAGE).get_page(request.GET.get("page"))
    everything = EquipmentItem.objects.exclude(status=EquipmentItem.Status.RETIRED)
    return {
        "page_obj": page_obj,
        "query": q,
        "kind": kind,
        "status": status,
        "filtered": bool(q or kind or status),
        "kpi_total": everything.count(),
        "kpi_stock": everything.filter(status=EquipmentItem.Status.IN_STOCK).count(),
        "kpi_repair": everything.filter(status=EquipmentItem.Status.REPAIR).count(),
    }


# ---------- Parc (RH, administrateur) ----------


def _item(public_id):
    return get_object_or_404(EquipmentItem.objects.select_related("holder"), public_id=public_id)


@require_GET
@module_required(Module.EQUIPMENT)
@permission_required("equipment.manage")
def item_detail(request, public_id):
    item = _item(public_id)
    context = {
        "item": item,
        "events": item.events.select_related("actor", "employee")[:50],
        "issues": item.issues.select_related("reported_by")[:20],
    }
    return render(request, "equipment/partials/item_modal.html", context)


@require_http_methods(["GET", "POST"])
@module_required(Module.EQUIPMENT)
@permission_required("equipment.manage")
def item_add(request):
    form = ItemForm(request.POST or None)
    template = "equipment/partials/item_form_modal.html"
    context = {"form": form, "action_url": reverse("equipment:item_add")}
    if request.method == "GET":
        return render(request, template, context)
    if form.is_valid():
        try:
            item = services.add_item(**form.cleaned_data, context=ActionContext.of(request))
        except services.EquipmentError as error:
            form.add_error(error.field, error.message)
    if not form.is_valid():
        return form_error_response(request, template, context)
    return after_action(
        request,
        Toast(title=_("Équipement ajouté"), message=f"{item.model} · {item.serial_number}"),
        refresh=CHANGED,
        close_modal=True,
    )


@require_http_methods(["GET", "POST"])
@module_required(Module.EQUIPMENT)
@permission_required("equipment.manage")
def item_assign(request, public_id):
    item = _item(public_id)
    form = AssignForm(request.POST or None)
    template = "equipment/partials/assign_modal.html"
    context = {
        "form": form,
        "item": item,
        "action_url": reverse("equipment:item_assign", args=[item.public_id]),
    }
    if request.method == "GET":
        return render(request, template, context)
    if not form.is_valid():
        return form_error_response(request, template, context)
    employee = form.cleaned_data["employee"]
    try:
        payload = services.assign(item, employee, context=ActionContext.of(request))
    except services.EquipmentError as error:
        return error_response(error, close_modal=True)
    return _assigned(request, item, employee, payload)


def _assigned(request, item, employee, payload):
    token = undo.make_token(request, "equipment.assign", json.dumps(payload))
    toast = Toast(
        title=_("Équipement attribué"),
        message=_("%(item)s remis à %(name)s.")
        % {"item": f"{item.get_kind_display()} {item.serial_number}", "name": employee.full_name},
        emphasis=employee.full_name,
        undo_url=reverse("equipment:undo", args=[token]),
    )
    return after_action(request, toast, refresh=(CHANGED, "requestsChanged"), close_modal=True)


UNDO_ACTIONS = {
    "equipment.assign": (
        services.undo_assign,
        gettext_lazy("Attribution annulée"),
        gettext_lazy("L'équipement est de nouveau en stock."),
    ),
    "equipment.repair": (
        services.undo_repair,
        gettext_lazy("Envoi en réparation annulé"),
        gettext_lazy("L'équipement a repris son état précédent."),
    ),
}


@require_POST
@module_required(Module.EQUIPMENT)
def undo_action(request, token):
    """« Annuler » dans la notification visuelle : 30 s, auteur seulement (L0-03)."""
    require(request, "equipment.manage")
    try:
        data = undo.read_token(request, token)
    except undo.UndoError as error:
        return error_response(error)
    if data.action not in UNDO_ACTIONS:
        raise Http404
    undo_service, title, message = UNDO_ACTIONS[data.action]
    try:
        undo_service(json.loads(data.target), context=ActionContext.of(request))
    except services.EquipmentError as error:
        return error_response(error)
    return after_action(
        request, Toast(title=str(title), message=str(message), kind="info"), refresh=CHANGED
    )


def _confirm_or_act(request, item, *, template_context, action, done_title):
    if request.method == "GET":
        return confirm_response(request, **template_context)
    try:
        action(item, context=ActionContext.of(request))
    except services.EquipmentError as error:
        return error_response(error, close_modal=True)
    return after_action(
        request,
        Toast(title=done_title, message=item.serial_number),
        refresh=CHANGED,
        close_modal=True,
    )


@require_http_methods(["GET", "POST"])
@module_required(Module.EQUIPMENT)
@permission_required("equipment.manage")
def item_return(request, public_id):
    item = _item(public_id)
    holder = item.holder.full_name if item.holder else ""
    return _confirm_or_act(
        request,
        item,
        template_context={
            "title": _("Enregistrer la restitution ?"),
            "text": _("%(item)s rendu par %(name)s. Il repasse en stock.")
            % {"item": f"{item.get_kind_display()} {item.serial_number}", "name": holder},
            "ok_label": _("Enregistrer la restitution"),
            "action_url": reverse("equipment:item_return", args=[item.public_id]),
        },
        action=services.return_item,
        done_title=_("Restitution enregistrée"),
    )


@require_http_methods(["GET", "POST"])
@module_required(Module.EQUIPMENT)
@permission_required("equipment.manage")
def item_retire(request, public_id):
    item = _item(public_id)
    return _confirm_or_act(
        request,
        item,
        template_context={
            "title": _("Retirer « %(item)s » du parc ?")
            % {"item": f"{item.get_kind_display()} {item.serial_number}"},
            "text": _("L'équipement passe à l'état « Retiré ». Son historique est conservé."),
            "ok_label": _("Retirer du parc"),
            "danger": True,
            "action_url": reverse("equipment:item_retire", args=[item.public_id]),
        },
        action=services.retire,
        done_title=_("Retiré du parc"),
    )


def _repair(request, item, *, action_url, send):
    """« Envoyer en réparation » : confirmation, puis « Annuler » pendant 30 s."""
    if request.method == "GET":
        holder = item.holder
        return confirm_response(
            request,
            title=_("Envoyer « %(item)s » en réparation ?")
            % {"item": f"{item.get_kind_display()} {item.serial_number}"},
            text=_("%(name)s reste son détenteur pendant la réparation.")
            % {"name": holder.full_name}
            if holder
            else _("L'équipement quitte le stock pendant la réparation."),
            ok_label=_("Envoyer en réparation"),
            action_url=action_url,
        )
    try:
        payload = send()
    except services.EquipmentError as error:
        return error_response(error, close_modal=True)
    token = undo.make_token(request, "equipment.repair", json.dumps(payload))
    toast = Toast(
        title=_("Envoyé en réparation"),
        message=item.serial_number,
        undo_url=reverse("equipment:undo", args=[token]),
    )
    return after_action(request, toast, refresh=CHANGED, close_modal=True)


@require_http_methods(["GET", "POST"])
@module_required(Module.EQUIPMENT)
@permission_required("equipment.manage")
def item_repair(request, public_id):
    item = _item(public_id)
    return _repair(
        request,
        item,
        action_url=reverse("equipment:item_repair", args=[item.public_id]),
        send=lambda: services.send_to_repair(item, context=ActionContext.of(request)),
    )


@require_POST
@module_required(Module.EQUIPMENT)
@permission_required("equipment.manage")
def item_back(request, public_id):
    item = _item(public_id)
    try:
        item = services.back_from_repair(item, context=ActionContext.of(request))
    except services.EquipmentError as error:
        return error_response(error, close_modal=True)
    title = _("Rendu à son détenteur") if item.holder_id else _("Remis en stock")
    return after_action(request, Toast(title=title, message=item.serial_number), refresh=CHANGED)


# ---------- Signalements ----------


@require_http_methods(["GET", "POST"])
@module_required(Module.EQUIPMENT)
def issue_new(request, public_id):
    """« Signaler un problème » : seulement sur un équipement que l'on détient."""
    item = get_object_or_404(EquipmentItem, public_id=public_id, holder=request.employee)
    form = IssueForm(request.POST or None)
    template = "equipment/partials/issue_modal.html"
    context = {
        "form": form,
        "item": item,
        "action_url": reverse("equipment:issue_new", args=[item.public_id]),
    }
    if request.method == "GET":
        return render(request, template, context)
    if not form.is_valid():
        return form_error_response(request, template, context)
    try:
        services.report_issue(
            item,
            context=ActionContext.of(request),
            description=form.cleaned_data["description"],
        )
    except services.EquipmentError as error:
        return error_response(error, close_modal=True)
    return after_action(
        request,
        Toast(title=_("Signalement envoyé"), message=_("Les RH sont notifiés.")),
        refresh=CHANGED,
        close_modal=True,
    )


def _issue(pk):
    return get_object_or_404(EquipmentIssue.objects.select_related("item", "reported_by"), pk=pk)


@require_http_methods(["GET", "POST"])
@module_required(Module.EQUIPMENT)
@permission_required("equipment.manage")
def issue_close(request, pk):
    issue = _issue(pk)
    form = CloseIssueForm(request.POST or None)
    template = "equipment/partials/close_issue_modal.html"
    context = {
        "form": form,
        "issue": issue,
        "action_url": reverse("equipment:issue_close", args=[issue.pk]),
    }
    if request.method == "GET":
        return render(request, template, context)
    if not form.is_valid():
        return form_error_response(request, template, context)
    try:
        services.close_issue(
            issue,
            context=ActionContext.of(request),
            resolution=form.cleaned_data["resolution"],
        )
    except services.EquipmentError as error:
        return error_response(error, close_modal=True)
    return after_action(
        request, Toast(title=_("Signalement clos")), refresh=CHANGED, close_modal=True
    )


@require_http_methods(["GET", "POST"])
@module_required(Module.EQUIPMENT)
@permission_required("equipment.manage")
def issue_repair(request, pk):
    issue = _issue(pk)
    return _repair(
        request,
        issue.item,
        action_url=reverse("equipment:issue_repair", args=[issue.pk]),
        send=lambda: services.issue_to_repair(issue, context=ActionContext.of(request)),
    )


# ---------- Demande validée : attribuer un équipement ----------


@require_http_methods(["GET", "POST"])
@module_required(Module.EQUIPMENT)
@permission_required("equipment.manage")
def request_assign(request, public_id):
    equipment_request = get_object_or_404(
        EquipmentRequest.objects.select_related("requester"),
        public_id=public_id,
        status=RequestStatus.APPROVED,
    )
    form = StockChoiceForm(request.POST or None, kind=equipment_request.kind)
    template = "equipment/partials/request_assign_modal.html"
    context = {
        "form": form,
        "obj": equipment_request,
        "summary": summary(equipment_request),
        "action_url": reverse("equipment:request_assign", args=[equipment_request.public_id]),
    }
    if request.method == "GET":
        return render(request, template, context)
    if not form.is_valid():
        return form_error_response(request, template, context)
    item = form.cleaned_data["item"]
    try:
        payload = services.assign(
            item,
            equipment_request.requester,
            context=ActionContext.of(request),
            equipment_request=equipment_request,
        )
    except services.EquipmentError as error:
        return error_response(error, close_modal=True)
    return _assigned(request, item, equipment_request.requester, payload)
