"""Administration (`/administration/`, Administrateur uniquement)."""

from datetime import timedelta

from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from apps.accounts import services as accounts
from apps.administration import services
from apps.administration.forms import (
    ClosureForm,
    CompanyForm,
    CompetencyForm,
    JournalFilterForm,
    StructureForm,
    UsersFilterForm,
)
from apps.careers import services as careers
from apps.careers.models import Competency
from apps.core import permissions
from apps.core.access import enabled_modules, permission_required
from apps.core.context import ActionContext
from apps.core.dates import compact_day_stamp
from apps.core.files import signed_url
from apps.core.htmx import (
    PAGE_CHANGED,
    RELOAD_PAGE,
    Toast,
    after_action,
    confirm_response,
    error_response,
    form_error_response,
    is_htmx,
    modal_form_response,
)
from apps.core.http import attachment
from apps.core.models import AuditLog, Company, Module
from apps.core.services import set_module
from apps.people import services as people
from apps.people.models import IN_POST_STATUSES, Employee, Role

USERS_CHANGED = "usersChanged"
STRUCTURE_CHANGED = "structureChanged"
MODULES_CHANGED = "modulesChanged"

TABS = [
    ("administration:company", gettext_lazy("Entreprise")),
    ("administration:competencies", gettext_lazy("Compétences")),
    ("administration:users", gettext_lazy("Utilisateurs et profils")),
    ("administration:structure", gettext_lazy("Services et sites")),
    ("administration:closures", gettext_lazy("Fermetures")),
    ("administration:modules", gettext_lazy("Modules")),
    ("administration:journal", gettext_lazy("Journal d'activité")),
]
CLOSURES_CHANGED = "closuresChanged"
COMPETENCIES_CHANGED = "competenciesChanged"

MODULE_DESCRIPTIONS = {
    Module.PLANNING: gettext_lazy("Présences, télétravail, congés, astreintes, export du planning"),
    Module.TELEWORK: gettext_lazy("Déclaration et validation"),
    Module.SUMMER_LEAVE: gettext_lazy("Campagne de vœux d'été"),
    Module.ON_CALL: gettext_lazy("Déclarations d'astreinte et d'intervention"),
    Module.TRANSPORT: gettext_lazy("Abonnements de transport"),
    Module.EQUIPMENT: gettext_lazy("Parc et attributions"),
    Module.INTERVENTIONS: gettext_lazy("Comptes rendus d'intervention par période"),
    Module.CAREERS: gettext_lazy("Entretiens et fiches de suivi"),
    Module.SURVEYS: gettext_lazy("Enquêtes internes"),
    Module.ANNOUNCEMENTS: gettext_lazy("Annonces"),
}


def tab_context(request, current: str) -> dict:
    # Les RH n'ont accès qu'aux fermetures, en lecture (L4-04).
    admin = permissions.can(request.employee, "admin.manage")
    return {
        "admin_tabs": [
            {"label": label, "url": reverse(name), "active": name == current}
            for name, label in TABS
            if admin or name == "administration:closures"
        ],
        "company": request.company,
    }


# ---------- Entreprise ----------


@require_http_methods(["GET", "POST"])
@permission_required("admin.manage")
def company(request):
    instance = Company.objects.get(pk=request.company.pk)
    form = CompanyForm(request.POST or None, request.FILES or None, instance=instance)
    if request.method == "POST" and form.is_valid():
        data = {name: form.cleaned_data[name] for name in CompanyForm.Meta.fields}
        services.update_company(
            instance,
            data,
            context=ActionContext.of(request),
            logo=form.cleaned_data.get("logo_upload"),
            remove_logo=bool(request.POST.get("remove_logo")),
        )
        toast = Toast(title=_("Paramètres enregistrés"))
        return after_action(request, toast, refresh=PAGE_CHANGED, page_form=True)
    context = {
        **tab_context(request, "administration:company"),
        "form": form,
        "logo_url": signed_url(instance.logo) if instance.logo else "",
    }
    return render(
        request, "administration/company.html", context, status=422 if form.errors else 200
    )


# ---------- Utilisateurs et profils ----------


@require_GET
@permission_required("admin.manage")
def users(request):
    form = UsersFilterForm(request.GET or None)
    form.is_valid()
    data = getattr(form, "cleaned_data", {})
    people_qs = Employee.objects.filter(status__in=IN_POST_STATUSES).select_related("user")
    if data.get("q"):
        q = data["q"]
        people_qs = people_qs.filter(
            Q(first_name__icontains=q) | Q(last_name__icontains=q) | Q(email__icontains=q)
        )
    if data.get("profil"):
        people_qs = people_qs.filter(role=data["profil"])
    page_obj = Paginator(people_qs, 8).get_page(request.GET.get("page"))
    latest = accounts.latest_open_invitations(page_obj.object_list)
    for person in page_obj.object_list:
        invitation = latest.get(person.pk)
        person.invitation_pending = invitation is not None
        person.invitation_failed = invitation is not None and invitation.send_failed
    context = {
        **tab_context(request, "administration:users"),
        "filter_form": form,
        "page_obj": page_obj,
        "roles": Role.choices,
        "results_url": reverse("administration:users"),
    }
    if is_htmx(request) and request.htmx.target == "results":
        return render(request, "administration/users.html#results", context)
    return render(request, "administration/users.html", context)


@require_http_methods(["GET", "POST"])
@permission_required("admin.manage")
def change_role(request, public_id):
    person = get_object_or_404(Employee, public_id=public_id, status__in=IN_POST_STATUSES)
    role = request.POST.get("role") or request.GET.get("role")
    if role not in Role.values:
        return HttpResponse(status=400)
    if request.method == "GET":
        context = {
            "person": person,
            "new_role": Role(role).label,
            "role": role,
            "action_url": reverse("administration:change_role", args=[person.public_id]),
        }
        return render(request, "administration/partials/role_modal.html", context)
    try:
        people.change_role(person, role, context=ActionContext.of(request))
    except people.PeopleError as error:
        return error_response(error, close_modal=True, refresh=USERS_CHANGED)
    return after_action(
        request,
        Toast(
            title=_("Profil modifié"),
            message=f"{person.full_name} : {Role(role).label}",
            emphasis=person.full_name,
        ),
        refresh=USERS_CHANGED,
        close_modal=True,
    )


@require_POST
@permission_required("admin.manage")
def send_invitation(request, public_id):
    person = get_object_or_404(Employee, public_id=public_id, status__in=IN_POST_STATUSES)
    try:
        accounts.invite(person, sent_by=request.employee, request=request)
    except accounts.InvitationError as error:
        return error_response(error)
    return after_action(
        request,
        Toast(
            title=_("Invitation envoyée"),
            message=_("Un lien valable 7 jours a été envoyé à %(email)s.")
            % {"email": person.email},
            emphasis=person.email,
        ),
        refresh=USERS_CHANGED,
    )


# ---------- Services et sites ----------


def _structure(kind):
    if kind not in services.STRUCTURES:
        from django.http import Http404

        raise Http404
    return services.STRUCTURES[kind]


@require_GET
@permission_required("admin.manage")
def structure(request):
    blocks = []
    for kind, (model, _field, label, _lower) in services.STRUCTURES.items():
        items = list(model.objects.order_by("name"))
        for item in items:
            item.usage = services.usage(kind, item)
        blocks.append(
            {
                "kind": kind,
                "label": _("Services") if kind == "services" else _("Sites"),
                "items": items,
                "singular": label,
            }
        )
    context = {**tab_context(request, "administration:structure"), "blocks": blocks}
    if is_htmx(request) and request.htmx.target == "structure":
        return render(request, "administration/structure.html#lists", context)
    return render(request, "administration/structure.html", context)


@require_http_methods(["GET", "POST"])
@permission_required("admin.manage")
def structure_form(request, kind, pk=None):
    model, _field, _label, lower = _structure(kind)
    instance = get_object_or_404(model, pk=pk) if pk else None
    initial = None
    if instance:
        initial = {
            "name": instance.name,
            "alsace_moselle": getattr(instance, "alsace_moselle", False),
        }
    form = StructureForm(request.POST or None, model=model, instance=instance, initial=initial)
    if pk:
        action_url = reverse("administration:structure_rename", args=[kind, pk])
        title = (_("Modifier « %(name)s »") if kind == "sites" else _("Renommer « %(name)s »")) % {
            "name": instance.name
        }
    else:
        action_url = reverse("administration:structure_add", args=[kind])
        title = _("Ajouter un %(kind)s") % {"kind": lower}
    template = "administration/partials/structure_modal.html"
    context = {"form": form, "action_url": action_url, "title": title, "is_rename": bool(pk)}
    if request.method == "POST":
        if not form.is_valid():
            return form_error_response(request, template, context)
        name = form.cleaned_data["name"]
        alsace = form.cleaned_data.get("alsace_moselle") if kind == "sites" else None
        if instance:
            services.rename_structure(
                kind, instance, name, context=ActionContext.of(request), alsace_moselle=alsace
            )
            toast = Toast(title=_("Modifié") if kind == "sites" else _("Renommé"), message=name)
        else:
            services.add_structure(
                kind, name, context=ActionContext.of(request), alsace_moselle=bool(alsace)
            )
            toast = Toast(title=_("Ajouté"), message=name)
        return after_action(request, toast, refresh=STRUCTURE_CHANGED, close_modal=True)
    return render(request, template, context)


@require_http_methods(["GET", "POST"])
@permission_required("admin.manage")
def structure_delete(request, kind, pk):
    model, field, _label, lower = _structure(kind)
    instance = get_object_or_404(model, pk=pk)
    count = services.usage(kind, instance)
    if request.method == "GET":
        context = {
            "item": instance,
            "count": count,
            "kind_label": lower,
            "directory_url": f"{reverse('people:list')}?{field}={instance.pk}",
            "action_url": reverse("administration:structure_delete", args=[kind, pk]),
        }
        template = (
            "administration/partials/structure_in_use_modal.html"
            if count
            else "administration/partials/structure_delete_modal.html"
        )
        return render(request, template, context)
    try:
        services.delete_structure(kind, instance, context=ActionContext.of(request))
    except services.AdministrationError as error:
        return error_response(error, close_modal=True)
    return after_action(
        request,
        Toast(title=_("Supprimé"), message=instance.name),
        refresh=STRUCTURE_CHANGED,
        close_modal=True,
    )


# ---------- Fermetures (T-16) ----------


@require_GET
@permission_required("closures.view")
def closures(request):
    from apps.agenda.models import Closure

    today = timezone.localdate()
    items = list(
        Closure.objects.filter(date__gte=today - timedelta(days=365)).select_related("site")
    )
    for item in items:
        item.scope = services.closure_scope(item)
        item.concerned = services.affected_telework(item) if item.date >= today else []
        item.is_past = item.date < today
    context = {
        **tab_context(request, "administration:closures"),
        "upcoming": [i for i in items if not i.is_past],
        "past": [i for i in items if i.is_past][::-1],
        "can_manage": permissions.can(request.employee, "closures.manage"),
    }
    if is_htmx(request) and request.htmx.target == "closures":
        return render(request, "administration/closures.html#lists", context)
    return render(request, "administration/closures.html", context)


@require_http_methods(["GET", "POST"])
@permission_required("closures.manage")
def closure_add(request):
    form = ClosureForm(request.POST or None)
    template = "administration/partials/closure_modal.html"
    context = {"form": form, "action_url": reverse("administration:closure_add")}
    if request.method == "POST":
        if not form.is_valid():
            return form_error_response(request, template, context)
        try:
            closure, concerned = services.add_closure(
                day=form.cleaned_data["date"],
                label=form.cleaned_data["label"],
                site=form.cleaned_data["site"],
                context=ActionContext.of(request),
            )
        except services.ClosureError as error:
            form.add_error(error.field, error.message)
            return form_error_response(request, template, context)
        message = closure.label
        if concerned:
            message = _(
                "%(label)s. %(n)s demande(s) de télétravail concernée(s) : les RH sont prévenus."
            ) % {"label": closure.label, "n": len(concerned)}
        return after_action(
            request,
            Toast(title=_("Fermeture ajoutée"), message=message),
            refresh=CLOSURES_CHANGED,
            close_modal=True,
        )
    return render(request, template, context)


@require_http_methods(["GET", "POST"])
@permission_required("closures.manage")
def closure_delete(request, pk):
    from apps.agenda.models import Closure

    closure = get_object_or_404(Closure.objects.select_related("site"), pk=pk)
    if request.method == "GET":
        return render(
            request,
            "administration/partials/closure_delete_modal.html",
            {
                "item": closure,
                "action_url": reverse("administration:closure_delete", args=[pk]),
            },
        )
    services.delete_closure(closure, context=ActionContext.of(request))
    return after_action(
        request,
        Toast(title=_("Fermeture supprimée"), message=closure.label),
        refresh=CLOSURES_CHANGED,
        close_modal=True,
    )


# ---------- Modules ----------


@require_GET
@permission_required("admin.manage")
def modules(request):
    enabled = enabled_modules(request)
    items = [
        {
            "key": key,
            "label": label,
            "description": MODULE_DESCRIPTIONS[key],
            "enabled": key in enabled,
        }
        for key, label in Module.choices
    ]
    context = {**tab_context(request, "administration:modules"), "modules": items}
    if is_htmx(request) and request.htmx.target == "modules":
        return render(request, "administration/modules.html#list", context)
    return render(request, "administration/modules.html", context)


@require_http_methods(["GET", "POST"])
@permission_required("admin.manage")
def toggle_module(request, module):
    if module not in Module.values:
        from django.http import Http404

        raise Http404
    label = Module(module).label
    enable = request.POST.get("enabled") == "1"
    if request.method == "GET":
        # Désactivation : confirmation (« Le module disparaîtra du menu… »).
        return render(
            request,
            "administration/partials/module_disable_modal.html",
            {
                "label": label,
                "action_url": reverse("administration:toggle_module", args=[module]),
            },
        )
    set_module(request.company, module, enable, context=ActionContext.of(request))
    title = _("Module activé") if enable else _("Module désactivé")
    # Le menu change aussi : toute la page se recharge.
    toast = Toast(title=title, message=label)
    return after_action(request, toast, refresh=RELOAD_PAGE, close_modal=True)


# ---------- Journal d'activité ----------


@require_GET
@permission_required("admin.manage")
def journal(request):
    form = JournalFilterForm(request.GET or None)
    form.is_valid()
    start, end = form.period()
    q = (getattr(form, "cleaned_data", {}) or {}).get("q", "")
    entries = services.journal(AuditLog.objects.all(), q=q, start=start, end=end)
    page_obj = Paginator(entries, 20).get_page(request.GET.get("page"))
    context = {
        **tab_context(request, "administration:journal"),
        "filter_form": form,
        "page_obj": page_obj,
        "start": start,
        "end": end,
        "results_url": reverse("administration:journal"),
        "export_url": f"{reverse('administration:journal_export')}?{request.GET.urlencode()}",
    }
    if is_htmx(request) and request.htmx.target == "results":
        return render(request, "administration/journal.html#results", context)
    return render(request, "administration/journal.html", context)


@require_GET
@permission_required("admin.manage")
def journal_export(request):
    form = JournalFilterForm(request.GET or None)
    if request.GET and not form.is_valid():
        return redirect("administration:journal")
    start, end = form.period()
    q = (getattr(form, "cleaned_data", {}) or {}).get("q", "")
    content = services.export_journal_csv(
        q=q, start=start, end=end, context=ActionContext.of(request)
    )
    filename = f"journal-{compact_day_stamp(start)}-{compact_day_stamp(end)}.csv"
    return attachment(content, "text/csv; charset=utf-8", filename)


# ---------- Compétences (lot 7) ----------


def _competency(pk) -> Competency:
    return get_object_or_404(Competency, pk=pk)


@require_GET
@permission_required("admin.manage")
def competencies(request):
    context = {
        **tab_context(request, "administration:competencies"),
        "competencies": list(Competency.objects.all()),
    }
    if is_htmx(request) and request.htmx.target == "competencies":
        return render(request, "administration/competencies.html#list", context)
    return render(request, "administration/competencies.html", context)


@require_http_methods(["GET", "POST"])
@permission_required("admin.manage")
def competency_form(request, pk=None):
    instance = _competency(pk) if pk else None
    initial = {"name": instance.name, "description": instance.description} if instance else None
    form = CompetencyForm(request.POST or None, initial=initial)
    action_url = (
        reverse("administration:competency_edit", args=[pk])
        if pk
        else reverse("administration:competency_add")
    )
    template = "administration/partials/competency_modal.html"
    context = {"form": form, "action_url": action_url, "competency": instance}
    if request.method == "POST" and form.is_valid():
        name, description = form.cleaned_data["name"], form.cleaned_data["description"]
        try:
            if instance:
                careers.update_competency(
                    instance, name, description, context=ActionContext.of(request)
                )
            else:
                careers.add_competency(name, description, context=ActionContext.of(request))
        except careers.CareerError as error:
            form.add_error(error.field if error.field in form.fields else None, error.message)
        else:
            toast = Toast(title=_("Modifiée") if instance else _("Ajoutée"), message=name)
            return after_action(request, toast, refresh=COMPETENCIES_CHANGED, close_modal=True)
    return modal_form_response(request, template, context)


@require_POST
@permission_required("admin.manage")
def competency_move(request, pk, step):
    careers.move_competency(_competency(pk), step, context=ActionContext.of(request))
    return after_action(request, Toast(title=_("Ordre enregistré")), refresh=COMPETENCIES_CHANGED)


@require_http_methods(["GET", "POST"])
@permission_required("admin.manage")
def competency_toggle(request, pk):
    competency = _competency(pk)
    action_url = reverse("administration:competency_toggle", args=[pk])
    if request.method == "GET" and competency.active:
        return confirm_response(
            request,
            title=_("Désactiver « %(name)s » ?") % {"name": competency.name},
            text=_(
                "Elle ne sera plus demandée dans les nouvelles évaluations. Les notes déjà "
                "données sont conservées."
            ),
            ok_label=_("Désactiver"),
            action_url=action_url,
            danger=True,
        )
    try:
        careers.set_competency_active(
            competency, not competency.active, context=ActionContext.of(request)
        )
    except careers.CareerError as error:
        return error_response(error, close_modal=True)
    title = _("Compétence réactivée") if competency.active else _("Compétence désactivée")
    return after_action(
        request,
        Toast(title=title, message=competency.name),
        refresh=COMPETENCIES_CHANGED,
        close_modal=True,
    )
