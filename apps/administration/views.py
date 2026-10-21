"""Administration (`/administration/`, Administrateur uniquement)."""

from datetime import timedelta

from django.contrib import messages
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
    JournalFilterForm,
    StructureForm,
    UsersFilterForm,
)
from apps.core import permissions
from apps.core.access import enabled_modules, permission_required
from apps.core.files import signed_url
from apps.core.htmx import Toast, is_htmx, toast_response, trigger
from apps.core.models import AuditLog, Company, Module
from apps.core.services import set_module
from apps.people import services as people
from apps.people.models import IN_POST_STATUSES, Employee, Role

USERS_CHANGED = "usersChanged"
STRUCTURE_CHANGED = "structureChanged"
MODULES_CHANGED = "modulesChanged"

TABS = [
    ("administration:company", gettext_lazy("Entreprise")),
    ("administration:users", gettext_lazy("Utilisateurs et profils")),
    ("administration:structure", gettext_lazy("Services et sites")),
    ("administration:closures", gettext_lazy("Fermetures")),
    ("administration:modules", gettext_lazy("Modules")),
    ("administration:journal", gettext_lazy("Journal d'activité")),
]
CLOSURES_CHANGED = "closuresChanged"

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


def _event(response, name):
    return trigger(response, **{name: True})


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
            actor=request.employee,
            logo=form.cleaned_data.get("logo_upload"),
            remove_logo=bool(request.POST.get("remove_logo")),
            request=request,
        )
        messages.success(request, _("Paramètres enregistrés"))
        return redirect("administration:company")
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
        people.change_role(person, role, actor=request.employee, request=request)
    except people.PeopleError as error:
        return _event(
            toast_response(
                Toast(title=str(error.message), kind="err"), close_modal=True, status=409
            ),
            USERS_CHANGED,
        )
    return _event(
        toast_response(
            Toast(
                title=_("Profil modifié"),
                message=f"{person.full_name} : {Role(role).label}",
                emphasis=person.full_name,
            ),
            close_modal=True,
        ),
        USERS_CHANGED,
    )


@require_POST
@permission_required("admin.manage")
def send_invitation(request, public_id):
    person = get_object_or_404(Employee, public_id=public_id, status__in=IN_POST_STATUSES)
    try:
        accounts.invite(person, sent_by=request.employee, request=request)
    except accounts.InvitationError as error:
        return toast_response(Toast(title=str(error.message), kind="err"), status=409)
    return _event(
        toast_response(
            Toast(
                title=_("Invitation envoyée"),
                message=_("Un lien valable 7 jours a été envoyé à %(email)s.")
                % {"email": person.email},
                emphasis=person.email,
            )
        ),
        USERS_CHANGED,
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
            return render(request, f"{template}#form", context, status=422)
        name = form.cleaned_data["name"]
        alsace = form.cleaned_data.get("alsace_moselle") if kind == "sites" else None
        if instance:
            services.rename_structure(
                kind, instance, name, actor=request.employee, request=request, alsace_moselle=alsace
            )
            toast = Toast(title=_("Modifié") if kind == "sites" else _("Renommé"), message=name)
        else:
            services.add_structure(
                kind, name, actor=request.employee, request=request, alsace_moselle=bool(alsace)
            )
            toast = Toast(title=_("Ajouté"), message=name)
        return _event(toast_response(toast, close_modal=True), STRUCTURE_CHANGED)
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
        services.delete_structure(kind, instance, actor=request.employee, request=request)
    except services.AdministrationError as error:
        return toast_response(
            Toast(title=str(error.message), kind="err"), close_modal=True, status=409
        )
    return _event(
        toast_response(Toast(title=_("Supprimé"), message=instance.name), close_modal=True),
        STRUCTURE_CHANGED,
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
            return render(request, f"{template}#form", context, status=422)
        try:
            closure, concerned = services.add_closure(
                day=form.cleaned_data["date"],
                label=form.cleaned_data["label"],
                site=form.cleaned_data["site"],
                actor=request.employee,
                request=request,
            )
        except services.ClosureError as error:
            form.add_error(error.field, error.message)
            return render(request, f"{template}#form", context, status=422)
        message = closure.label
        if concerned:
            message = _(
                "%(label)s. %(n)s demande(s) de télétravail concernée(s) : les RH sont prévenus."
            ) % {"label": closure.label, "n": len(concerned)}
        return _event(
            toast_response(Toast(title=_("Fermeture ajoutée"), message=message), close_modal=True),
            CLOSURES_CHANGED,
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
    services.delete_closure(closure, actor=request.employee, request=request)
    return _event(
        toast_response(
            Toast(title=_("Fermeture supprimée"), message=closure.label), close_modal=True
        ),
        CLOSURES_CHANGED,
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
    set_module(request.company, module, enable, actor=request.employee, request=request)
    title = _("Module activé") if enable else _("Module désactivé")
    response = toast_response(Toast(title=title, message=label), close_modal=True)
    response["HX-Refresh"] = "true"  # le menu de la page change aussi
    return response


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
        q=q, start=start, end=end, actor=request.employee, request=request
    )
    response = HttpResponse(content, content_type="text/csv; charset=utf-8")
    filename = f"journal-{start:%Y%m%d}-{end:%Y%m%d}.csv"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
