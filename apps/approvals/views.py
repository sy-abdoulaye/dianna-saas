"""Écrans des demandes (gabarit commun, docs/modules/05-demandes.md). Toutes les adresses
d'un module passent par `module_required` : module désactivé → page « Module désactivé ».
Aucune transition dans une vue : tout passe par apps/approvals/workflow.py."""

import json
from functools import wraps

from django.core.paginator import Paginator
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from apps.approvals import rules, workflow
from apps.approvals.forms import FORMS, CampaignForm, ReasonForm
from apps.approvals.kinds import KINDS, summary
from apps.approvals.models import (
    REQUEST_MODELS,
    LeaveRequest,
    RequestStatus,
    SummerCampaign,
    TeleworkRequest,
)
from apps.core import permissions, undo
from apps.core.access import module_is_enabled, require
from apps.core.htmx import Toast, is_htmx, toast_response, trigger
from apps.core.models import Module

CHANGED = "requestsChanged"
TAB_MINE, TAB_TODO, TAB_TEAM = "mes-demandes", "a-valider", "equipe"
PER_PAGE = 8


def module_view(view):
    """Vérifie le module de `kind` (« Module désactivé ») avant la vue."""

    @wraps(view)
    def wrapper(request, kind, *args, **kwargs):
        if kind not in KINDS:
            raise Http404
        module = KINDS[kind].model.module
        if not module_is_enabled(request, module):
            from apps.core.views import module_disabled

            return module_disabled(request, Module(module).label)
        return view(request, kind, *args, **kwargs)

    return wrapper


def _changed(response):
    return trigger(response, **{CHANGED: True})


def is_validator(employee) -> bool:
    return employee.has_reports or workflow.is_hr_or_admin(employee)


def get_request(request, kind, public_id):
    """Demande visible par la personne connectée ; sinon 404 (jamais 403 : l'existence d'une
    demande hors périmètre n'est pas révélée)."""
    model = KINDS[kind].model
    obj = get_object_or_404(
        model.objects.select_related(
            "requester", "requester__service", "requester__manager", "requester__company"
        ),
        public_id=public_id,
    )
    me = request.employee
    if not (
        obj.requester_id == me.pk
        or permissions.can(me, "requests.view", obj)
        or workflow.can_decide(me, obj)
    ):
        raise Http404
    return obj


# ---------- Page du module ----------


@require_GET
@module_view
def request_list(request, kind):
    me = request.employee
    meta = KINDS[kind]
    model = meta.model
    tabs = [(TAB_MINE, _("Mes demandes"), 0)]
    todo = workflow.to_validate(me, model) if is_validator(me) else model.objects.none()
    if is_validator(me):
        tabs.append((TAB_TODO, _("À valider"), todo.count()))
    if workflow.is_hr_or_admin(me):
        tabs.append((TAB_TEAM, _("Toutes les demandes"), 0))
    elif me.has_reports:
        tabs.append((TAB_TEAM, _("Mon équipe"), 0))
    tab = request.GET.get("onglet", TAB_MINE)
    if tab not in {key for key, _label, _n in tabs}:
        tab = TAB_MINE

    if tab == TAB_MINE:
        rows = model.objects.filter(requester=me)
    elif tab == TAB_TODO:
        rows = todo
    else:
        rows = permissions.scope_queryset(me, model.objects.all(), "requests.view").exclude(
            requester=me
        )
    rows = rows.select_related("requester", "requester__service", "requester__manager")
    q = request.GET.get("q", "").strip()
    status = request.GET.get("statut", "")
    if q:
        rows = rows.filter(
            Q(requester__first_name__icontains=q) | Q(requester__last_name__icontains=q)
        )
    if status in RequestStatus.values:
        rows = rows.filter(status=status)
    page_obj = Paginator(rows.order_by("-submitted_at", "-pk"), PER_PAGE).get_page(
        request.GET.get("page")
    )
    for row in page_obj.object_list:
        _decorate(row, me, tab)

    url = reverse(meta.url_name)
    context = {
        "kind": meta,
        "tab": tab,
        "tabs": [
            {"label": label, "url": f"{url}?onglet={key}", "count": count, "active": key == tab}
            for key, label, count in tabs
        ],
        "page_obj": page_obj,
        "list_url": url,
        "filtered": bool(q or status),
        "query": q,
        "status_choices": [
            ("", _("Tous")),
            ("pending", _("En attente")),
            ("approved", _("Validées")),
            ("refused", _("Refusées")),
            ("cancelled", _("Annulées")),
        ],
        "status": status,
        "new_url": reverse("approvals:new", args=[kind]),
        "is_hr": workflow.is_hr_or_admin(me),
    }
    context.update(_module_block(me, kind))
    if is_htmx(request) and request.htmx.target == "results":
        return render(request, "approvals/requests.html#results", context)
    return render(request, "approvals/requests.html", context)


def _decorate(row, me, tab):
    row.summary = summary(row)
    row.can_decide = workflow.can_decide(me, row)
    row.can_cancel = row.requester_id == me.pk and row.is_open
    # Alerte de conflit : seulement pour qui peut décider (A3-03).
    row.conflict = (
        rules.conflicts_of(row)
        if isinstance(row, LeaveRequest) and row.is_open and row.can_decide
        else None
    )


def _module_block(me, kind) -> dict:
    if kind == "telework":
        today = rules.today()
        return {
            "week_used": rules.telework_days_in_week(me, today),
            "quota": rules.weekly_quota(me),
            "pending_count": TeleworkRequest.objects.filter(
                requester=me, status=RequestStatus.PENDING
            ).count(),
        }
    if kind == "leave":
        return {"campaign": rules.open_campaign()}
    return {}


# ---------- Création ----------


@require_http_methods(["GET", "POST"])
@module_view
def new_request(request, kind):
    me = request.employee
    require(request, "requests.create")
    meta = KINDS[kind]
    form_class = FORMS[kind]
    template = "approvals/partials/form_modal.html"
    action_url = reverse("approvals:new", args=[kind])
    initial = {"date": request.GET.get("date")} if kind == "telework" else None
    if request.method == "GET":
        form = form_class(requester=me, initial=initial)
        return render(request, template, _form_context(meta, form, action_url))
    form = form_class(request.POST, requester=me)
    if form.is_valid():
        try:
            result = workflow.submit(meta.model, me, form.model_data(), http_request=request)
        except workflow.RequestValidationError as error:
            for name, message in error.errors.items():
                form.add_error(name if name in form.fields else None, message)
    if not form.is_valid():
        return render(
            request, f"{template}#form", _form_context(meta, form, action_url), status=422
        )
    return _with_undo(request, result, "submit", _submit_toast(result))


def _form_context(meta, form, action_url):
    return {"kind": meta, "form": form, "action_url": action_url, "destination": None}


def _submit_toast(result) -> Toast:
    req = result.request
    if result.auto_approved:
        return Toast(
            title=_("Demande validée"),
            message=_("%(summary)s : validée automatiquement.") % {"summary": summary(req)},
        )
    manager = workflow.active_manager(req.requester)
    dest = manager.full_name if manager else _("l'équipe RH")
    message = _("%(summary)s transmise à %(dest)s.") % {"summary": summary(req), "dest": dest}
    return Toast(title=_("Demande envoyée"), message=message, emphasis=summary(req))


def _with_undo(request, result, action, toast: Toast):
    token = undo.make_token(request, f"requests.{action}", json.dumps(result.undo_payload(action)))
    toast = Toast(**{**toast.__dict__, "undo_url": reverse("approvals:undo", args=[token])})
    return _changed(toast_response(toast, close_modal=True))


# ---------- Détail et décisions ----------


@require_GET
@module_view
def detail(request, kind, public_id):
    obj = get_request(request, kind, public_id)
    me = request.employee
    can_decide = workflow.can_decide(me, obj)
    context = {
        "kind": KINDS[kind],
        "obj": obj,
        "summary": summary(obj),
        "history": workflow.history(obj),
        # Noms et nombre des autres absents : seulement pour qui décide (A3-03).
        "conflict": rules.conflicts_of(obj)
        if isinstance(obj, LeaveRequest) and can_decide
        else None,
        "can_decide": can_decide,
        "acting_for": workflow.acting_for(me, obj),
        "can_cancel": obj.requester_id == me.pk and obj.is_open,
        "can_cancel_approved": workflow.can_cancel_approved(me, obj),
        "urls": _urls(kind, obj),
    }
    return render(request, "approvals/partials/detail_modal.html", context)


def _urls(kind, obj):
    return {
        name: reverse(f"approvals:{name}", args=[kind, obj.public_id])
        for name in ("approve", "refuse", "cancel", "cancel_approved")
    }


def _decision_error(error):
    return _changed(
        toast_response(Toast(title=str(error.message), kind="err"), close_modal=True, status=409)
    )


@require_POST
@module_view
def approve(request, kind, public_id):
    obj = get_request(request, kind, public_id)
    try:
        result = workflow.approve(obj, request.employee, http_request=request)
    except workflow.WorkflowError as error:
        return _decision_error(error)
    title = (
        _("Validée par le manager")
        if result.request.status == RequestStatus.MANAGER_APPROVED
        else _("Demande validée")
    )
    name = obj.requester.full_name
    toast = Toast(
        title=title,
        message=_("%(name)s a reçu une notification dans Dianna.") % {"name": name},
        emphasis=name,
    )
    return _with_undo(request, result, "approve", toast)


@require_http_methods(["GET", "POST"])
@module_view
def refuse(request, kind, public_id):
    obj = get_request(request, kind, public_id)
    if not workflow.can_decide(request.employee, obj):
        raise Http404
    form = ReasonForm(
        request.POST or None,
        label=_("Motif du refus"),
        required_message=_("Indiquez le motif du refus."),
    )
    context = {
        "obj": obj,
        "summary": summary(obj),
        "form": form,
        "action_url": reverse("approvals:refuse", args=[kind, obj.public_id]),
        "title": _("Refuser la demande"),
        "submit_label": _("Refuser la demande"),
    }
    template = "approvals/partials/reason_modal.html"
    if request.method == "GET":
        return render(request, template, context)
    if not form.is_valid():
        return render(request, f"{template}#form", context, status=422)
    try:
        result = workflow.refuse(
            obj, request.employee, reason=form.cleaned_data["reason"], http_request=request
        )
    except workflow.WorkflowError as error:
        return _decision_error(error)
    name = obj.requester.full_name
    toast = Toast(
        title=_("Demande refusée"),
        message=_("%(name)s a reçu une notification dans Dianna.") % {"name": name},
        emphasis=name,
    )
    return _with_undo(request, result, "refuse", toast)


@require_http_methods(["GET", "POST"])
@module_view
def cancel(request, kind, public_id):
    obj = get_request(request, kind, public_id)
    if obj.requester_id != request.employee.pk:
        raise Http404
    if request.method == "GET":
        return render(
            request,
            "approvals/partials/cancel_modal.html",
            {
                "obj": obj,
                "summary": summary(obj),
                "action_url": reverse("approvals:cancel", args=[kind, obj.public_id]),
            },
        )
    try:
        result = workflow.cancel(obj, request.employee, http_request=request)
    except workflow.WorkflowError as error:
        return _decision_error(error)
    return _with_undo(request, result, "cancel", Toast(title=_("Demande annulée")))


@require_http_methods(["GET", "POST"])
@module_view
def cancel_approved(request, kind, public_id):
    obj = get_request(request, kind, public_id)
    if not workflow.can_cancel_approved(request.employee, obj):
        raise Http404
    form = ReasonForm(
        request.POST or None,
        label=_("Motif de l'annulation"),
        required_message=_("Indiquez le motif de l'annulation."),
    )
    context = {
        "obj": obj,
        "summary": summary(obj),
        "form": form,
        "action_url": reverse("approvals:cancel_approved", args=[kind, obj.public_id]),
        "title": _("Annuler une demande validée"),
        "submit_label": _("Annuler la demande"),
    }
    template = "approvals/partials/reason_modal.html"
    if request.method == "GET":
        return render(request, template, context)
    if not form.is_valid():
        return render(request, f"{template}#form", context, status=422)
    try:
        result = workflow.cancel_approved(
            obj, request.employee, reason=form.cleaned_data["reason"], http_request=request
        )
    except workflow.WorkflowError as error:
        return _decision_error(error)
    name = obj.requester.full_name
    toast = Toast(
        title=_("Demande annulée"),
        message=_("%(name)s a reçu une notification dans Dianna.") % {"name": name},
        emphasis=name,
    )
    return _with_undo(request, result, "cancel_approved", toast)


@require_POST
def undo_transition(request, token):
    """« Annuler » dans la notification visuelle : 30 s, auteur seulement (L0-03)."""
    try:
        payload = undo.read_token(request, token)
    except undo.UndoError as error:
        return toast_response(Toast(title=str(error.message), kind="err"), status=409)
    data = json.loads(payload.target)
    model = REQUEST_MODELS.get(data.get("type"))
    if model is None or payload.action != f"requests.{data.get('action')}":
        raise Http404
    if not module_is_enabled(request, model.module):
        raise Http404
    try:
        restored = workflow.undo(model, data, request.employee, http_request=request)
    except workflow.WorkflowError as error:
        return toast_response(Toast(title=str(error.message), kind="err"), status=409)
    if restored is None:
        toast = Toast(title=_("Envoi annulé"), message=_("La demande a été retirée."), kind="info")
    else:
        toast = Toast(
            title=_("Décision annulée"),
            message=_("La demande est de nouveau en attente.")
            if restored.is_open
            else _("La demande est rétablie."),
            kind="info",
        )
    return _changed(toast_response(toast))


# ---------- Campagnes de congés d'été (RH) ----------

CAMPAIGNS_CHANGED = "campaignsChanged"


def _campaign_module(request):
    if not module_is_enabled(request, Module.SUMMER_LEAVE):
        from apps.core.views import module_disabled

        return module_disabled(request, Module(Module.SUMMER_LEAVE).label)
    require(request, "requests.manage_campaigns")
    return None


@require_GET
def campaigns(request):
    blocked = _campaign_module(request)
    if blocked:
        return blocked
    items = list(SummerCampaign.objects.all())
    for item in items:
        item.request_count = item.requests.exclude(status=RequestStatus.CANCELLED).count()
    return render(
        request,
        "approvals/campaigns.html",
        {
            "campaigns": items,
            "has_open": any(c.status == "open" for c in items),
            "leave_url": reverse("approvals:list", args=["leave"]),
        },
    )


@require_http_methods(["GET", "POST"])
def new_campaign(request):
    blocked = _campaign_module(request)
    if blocked:
        return blocked
    form = CampaignForm(request.POST or None)
    template = "approvals/partials/campaign_modal.html"
    if request.method == "POST":
        if not form.is_valid():
            return render(request, f"{template}#form", {"form": form}, status=422)
        campaign = form.save()
        from apps.core import audit

        audit.log(
            "requests.campaign_created",
            _("Campagne créée : %(l)s") % {"l": campaign.label},
            actor=request.employee,
            target=campaign,
            request=request,
        )
        return trigger(
            toast_response(
                Toast(title=_("Campagne créée"), message=campaign.label), close_modal=True
            ),
            **{CAMPAIGNS_CHANGED: True},
        )
    return render(request, template, {"form": form})


@require_POST
def campaign_status(request, pk, action):
    blocked = _campaign_module(request)
    if blocked:
        return blocked
    campaign = get_object_or_404(SummerCampaign, pk=pk)
    services = {"ouvrir": workflow.open_summer_campaign, "clore": workflow.close_summer_campaign}
    if action not in services:
        raise Http404
    try:
        campaign = services[action](campaign, request.employee, http_request=request)
    except workflow.WorkflowError as error:
        return toast_response(Toast(title=str(error.message), kind="err"), status=409)
    title = _("Campagne ouverte") if action == "ouvrir" else _("Campagne close")
    return trigger(
        toast_response(Toast(title=title, message=campaign.label)), **{CAMPAIGNS_CHANGED: True}
    )


# ---------- Compteurs du menu et fiche annuaire ----------

NAV_KEYS = {"telework": "telework", "leave": "summer_leave", "on_call": "on_call"}


def menu_counts(request) -> dict:
    """Compteurs « à traiter » par module (identiques à l'onglet « À valider »)."""
    me = getattr(request, "employee", None)
    if me is None or not is_validator(me):
        return {}
    counts = {}
    for kind, meta in KINDS.items():
        if module_is_enabled(request, meta.model.module):
            counts[NAV_KEYS[kind]] = workflow.to_validate(me, meta.model).count()
    return counts


def requests_of(request, employee) -> list:
    """Onglet « Demandes » de la fiche : soi, manager direct, RH (fiche annuaire)."""
    rows = []
    for meta in KINDS.values():
        if not module_is_enabled(request, meta.model.module):
            continue
        for obj in meta.model.objects.filter(requester=employee):
            obj.summary = summary(obj)
            obj.kind_meta = meta
            rows.append(obj)
    return sorted(rows, key=lambda r: r.submitted_at, reverse=True)
