"""Écrans des demandes (gabarit commun, docs/modules/05-demandes.md). Toutes les adresses
d'un module passent par `module_required` : module désactivé → page « Module désactivé ».
Aucune transition dans une vue : tout passe par apps/approvals/workflow.py."""

import json
from functools import wraps

from django.core.paginator import Paginator
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from apps.approvals import exports, rules, selectors, workflow
from apps.approvals.forms import (
    FORMS,
    CampaignExportForm,
    CampaignForm,
    MonthExportForm,
    ReasonForm,
    RequestFilterForm,
)
from apps.approvals.kinds import KINDS, euros, summary
from apps.approvals.models import (
    REQUEST_MODELS,
    LeaveRequest,
    RequestStatus,
    SummerCampaign,
    TeleworkRequest,
)
from apps.approvals.selectors import TAB_MINE, is_validator
from apps.core import permissions, undo
from apps.core.access import module_is_enabled, require
from apps.core.context import ActionContext
from apps.core.files import (
    StorageUnavailableError,
    storage_unavailable_response,
)
from apps.core.htmx import (
    Toast,
    after_action,
    download_response,
    error_response,
    form_error_response,
    is_htmx,
)
from apps.core.models import Module
from apps.core.ratelimit import (
    EXPORT_LIMIT_MESSAGE,
    export_allowed,
    export_limited_response,
    record_export,
)

CHANGED = "requestsChanged"
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
        or permissions.can(me, model.view_action, obj)
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
    tabs, todo = selectors.request_tabs(me, model)
    tab = request.GET.get("onglet", TAB_MINE)
    if tab not in {key for key, _label, _n in tabs}:
        tab = TAB_MINE
    q = request.GET.get("q", "").strip()
    status = request.GET.get("statut", "")
    rows = selectors.request_rows(me, model, tab, todo, q=q, status=status)
    page_obj = Paginator(rows, PER_PAGE).get_page(request.GET.get("page"))
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
        "filter_form": RequestFilterForm(request.GET, tab=tab, mine=tab == TAB_MINE),
        "status": status,
        "new_url": reverse("approvals:new", args=[kind]),
        "is_hr": workflow.is_hr_or_admin(me),
        "can_export": permissions.can(me, "requests.export"),
        # Lien vers le planning (L3-18) : seulement si le module Planning est activé.
        "planning_url": reverse("planning:week")
        if module_is_enabled(request, Module.PLANNING) and model.calendar_kind
        else "",
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
    require(request, KINDS[kind].model.create_action)
    meta = KINDS[kind]
    form_class = FORMS[kind]
    template = "approvals/partials/form_modal.html"
    action_url = reverse("approvals:new", args=[kind])
    initial = {"date": request.GET.get("date")} if kind == "telework" else None
    if request.method == "GET":
        form = form_class(requester=me, initial=initial)
        return render(request, template, _form_context(meta, form, action_url))
    form = form_class(request.POST, request.FILES, requester=me)
    if form.is_valid():
        try:
            result = workflow.submit(
                meta.model, form.model_data(), context=ActionContext(me, request)
            )
        except StorageUnavailableError:
            return storage_unavailable_response(request)
        except workflow.RequestValidationError as error:
            for name, message in error.errors.items():
                form.add_error(name if name in form.fields else None, message)
    if not form.is_valid():
        return form_error_response(request, template, _form_context(meta, form, action_url))
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
    if req.hr_validated:
        # Justificatifs et matériel : validés par les RH (L5-04).
        message = _("%(summary)s transmise aux RH.") % {"summary": summary(req)}
        return Toast(title=_("Demande envoyée"), message=message, emphasis=summary(req))
    manager = workflow.active_manager(req.requester)
    dest = manager.full_name if manager else _("l'équipe RH")
    message = _("%(summary)s transmise à %(dest)s.") % {"summary": summary(req), "dest": dest}
    return Toast(title=_("Demande envoyée"), message=message, emphasis=summary(req))


def _with_undo(request, result, action, toast: Toast):
    token = undo.make_token(request, f"requests.{action}", json.dumps(result.undo_payload(action)))
    toast = Toast(**{**toast.__dict__, "undo_url": reverse("approvals:undo", args=[token])})
    return after_action(request, toast, refresh=CHANGED, close_modal=True)


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
    if kind == "transport":
        context["proof_url"] = reverse("approvals:proof_file", args=[obj.public_id])
        context["refund"] = euros(obj.amount / 2)
    return render(request, "approvals/partials/detail_modal.html", context)


def _urls(kind, obj):
    return {
        name: reverse(f"approvals:{name}", args=[kind, obj.public_id])
        for name in ("approve", "refuse", "cancel", "cancel_approved")
    }


def _decision_error(error):
    """Refus d'une décision : erreur, et la liste se recharge (la demande a changé)."""
    return error_response(error, close_modal=True, refresh=CHANGED)


@require_POST
@module_view
def approve(request, kind, public_id):
    obj = get_request(request, kind, public_id)
    try:
        result = workflow.approve(obj, context=ActionContext.of(request))
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
        return form_error_response(request, template, context)
    try:
        result = workflow.refuse(
            obj, reason=form.cleaned_data["reason"], context=ActionContext.of(request)
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
        result = workflow.cancel(obj, context=ActionContext.of(request))
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
        return form_error_response(request, template, context)
    try:
        result = workflow.cancel_approved(
            obj, reason=form.cleaned_data["reason"], context=ActionContext.of(request)
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


def _undo_request(request, payload) -> Toast:
    """Annulation d'une transition de demande (vue commune apps.core.views.undo_action)."""
    data = json.loads(payload.target)
    model = REQUEST_MODELS.get(data.get("type"))
    if model is None or payload.action != f"requests.{data.get('action')}":
        raise Http404
    if not module_is_enabled(request, model.module):
        raise Http404
    restored = workflow.undo(model, data, context=ActionContext.of(request))
    if restored is None:
        return Toast(title=_("Envoi annulé"), message=_("La demande a été retirée."), kind="info")
    return Toast(
        title=_("Décision annulée"),
        message=_("La demande est de nouveau en attente.")
        if restored.is_open
        else _("La demande est rétablie."),
        kind="info",
    )


for _action in ("submit", "approve", "refuse", "cancel", "cancel_approved"):
    undo.register(f"requests.{_action}", _undo_request, refresh=CHANGED)


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
            return form_error_response(request, template, {"form": form})
        campaign = workflow.create_summer_campaign(
            form.cleaned_data, context=ActionContext.of(request)
        )
        toast = Toast(title=_("Campagne créée"), message=campaign.label)
        return after_action(request, toast, refresh=CAMPAIGNS_CHANGED, close_modal=True)
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
        campaign = services[action](campaign, context=ActionContext.of(request))
    except workflow.WorkflowError as error:
        return error_response(error)
    title = _("Campagne ouverte") if action == "ouvrir" else _("Campagne close")
    return after_action(
        request, Toast(title=title, message=campaign.label), refresh=CAMPAIGNS_CHANGED
    )


# ---------- Justificatifs de transport (L5-01) ----------


@require_GET
def proof_file(request, public_id):
    """Justificatif servi seulement à une personne connectée qui a la permission de le voir,
    contrôlée à chaque téléchargement (jamais de lien signé). Fichier isolé : type exact,
    `nosniff`, `sandbox`. Toute consultation par une autre personne que le demandeur (RH,
    administrateur) est inscrite au journal d'audit, sans nom de fichier."""
    from apps.core.files import serve_isolated

    if not module_is_enabled(request, Module.TRANSPORT):
        raise Http404
    obj = get_request(request, "transport", public_id)
    try:
        response = serve_isolated(
            obj.file,
            content_type=obj.file_type,
            filename=obj.original_name or "justificatif",
            inline=request.GET.get("telecharger") != "1",
        )
    except StorageUnavailableError:
        return storage_unavailable_response(request)
    workflow.record_proof_access(obj, context=ActionContext.of(request))
    return response


# ---------- Exports RH (L3-08) ----------

EXPORTABLE = {"telework", "on_call", "leave", "transport"}


def _download(content, content_type, filename):
    response = HttpResponse(content, content_type=content_type)
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@require_GET
@module_view
def export_requests(request, kind):
    """« Exporter » des RH : récapitulatif du mois (télétravail, astreintes) ou synthèse de
    campagne (congés). Sans paramètre : la modale ; avec : le fichier (via HX-Redirect)."""
    if kind not in EXPORTABLE:
        raise Http404
    require(request, "requests.export")
    me = request.employee
    action_url = reverse("approvals:export", args=[kind])
    form_class = CampaignExportForm if kind == "leave" else MonthExportForm
    form = form_class(request.GET if "format" in request.GET else None)
    context = {"form": form, "action_url": action_url, "kind": KINDS[kind]}
    template = "approvals/partials/export_modal.html"
    if "format" not in request.GET:
        return render(request, template, context)
    # Modale : message dans le formulaire ; téléchargement direct : page « Trop d'exports ».
    if is_htmx(request) and form.is_valid() and not export_allowed(me):
        form.add_error(None, EXPORT_LIMIT_MESSAGE)
    if not form.is_valid():
        return form_error_response(request, template, context)
    if is_htmx(request):
        return download_response(f"{action_url}?{request.GET.urlencode()}")
    if not record_export(me):
        return export_limited_response(request, reverse(KINDS[kind].url_name))
    return _download(*exports.export_file(kind, me, form.cleaned_data, request=request))


@require_GET
def campaign_summary(request, pk):
    blocked = _campaign_module(request)
    if blocked:
        return blocked
    require(request, "requests.export")
    campaign = get_object_or_404(SummerCampaign, pk=pk)
    fmt = request.GET.get("format")
    if fmt in exports.FORMAT_LABELS:
        if not record_export(request.employee):
            return export_limited_response(request, request.path)
        return _download(*exports.campaign_file(request.employee, campaign, fmt, request=request))
    mondays, summaries = exports.campaign_summary(campaign)
    return render(
        request,
        "approvals/campaign_summary.html",
        {
            "campaign": campaign,
            "mondays": mondays,
            "summaries": summaries,
            "campaigns_url": reverse("approvals:campaigns"),
            "planning_url": reverse("planning:week")
            if module_is_enabled(request, Module.PLANNING)
            else "",
        },
    )


# ---------- Compteurs du menu et fiche annuaire ----------

NAV_KEYS = {
    "telework": "telework",
    "leave": "summer_leave",
    "on_call": "on_call",
    "transport": "transport",
    "equipment": "equipment",
}


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
