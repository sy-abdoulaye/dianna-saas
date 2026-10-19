"""Annuaire (docs/modules/03-annuaire.md). Contrôles serveur : apps.core.permissions."""

import json
import uuid

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views import View
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from apps.accounts import services as accounts
from apps.core import permissions, undo
from apps.core.access import PermissionRequiredMixin, permission_required, require
from apps.core.files import signed_url
from apps.core.htmx import Toast, is_htmx, toast_response, trigger
from apps.people import importer, services
from apps.people.forms import (
    STATUS_IN_POST,
    STATUS_LEFT,
    ArchiveForm,
    ContactForm,
    DirectoryFilterForm,
    EmployeeForm,
    ImportUploadForm,
)
from apps.people.models import IN_POST_STATUSES, Employee, EmployeeStatus

VIEW_SESSION_KEY = "people_view"
PER_PAGE = {"liste": 8, "cartes": 12}
CHANGED_EVENT = "peopleChanged"


def photo_url(employee) -> str:
    """URL signée de la photo : tout salarié de l'entreprise voit l'annuaire (people.view_list)."""
    return signed_url(employee.photo) if employee.photo else ""


def get_employee(request, public_id) -> Employee:
    """Fiche de l'entreprise courante ; une fiche « Parti » n'existe pas pour qui ne peut pas
    voir les départs (404, sans révéler son existence)."""
    employee = get_object_or_404(
        Employee.objects.select_related("service", "site", "manager", "user"), public_id=public_id
    )
    if employee.status == EmployeeStatus.LEFT and not permissions.can(
        request.employee, "people.view_left"
    ):
        raise Http404
    return employee


# ---------- Liste ----------


class DirectoryView(PermissionRequiredMixin, View):
    permission = "people.view_list"
    template_name = "people/directory.html"

    def get(self, request):
        me = request.employee
        can_see_left = permissions.can(me, "people.view_left")
        form = DirectoryFilterForm(request.GET or None, show_status=can_see_left)
        form.is_valid()
        data = getattr(form, "cleaned_data", {})
        people = Employee.objects.select_related("service", "site", "manager")
        status = data.get("statut") or STATUS_IN_POST
        if not can_see_left or status == STATUS_IN_POST:
            people = people.filter(status__in=IN_POST_STATUSES)
        elif status == STATUS_LEFT:
            people = people.filter(status=EmployeeStatus.LEFT)
        q = (data.get("q") or "").strip()
        if q:
            people = people.filter(
                Q(first_name__icontains=q)
                | Q(last_name__icontains=q)
                | Q(job_title__icontains=q)
                | Q(email__icontains=q)
                | Q(service__name__icontains=q)
            )
        if data.get("service"):
            people = people.filter(service=data["service"])
        if data.get("site"):
            people = people.filter(site=data["site"])
        view = request.GET.get("vue") or request.session.get(VIEW_SESSION_KEY, "liste")
        view = view if view in PER_PAGE else "liste"
        request.session[VIEW_SESSION_KEY] = view  # sélecteur mémorisé
        page_obj = Paginator(people, PER_PAGE[view]).get_page(request.GET.get("page"))
        for person in page_obj.object_list:
            person.photo_url = photo_url(person)
            person.can_archive = not services.archive_refusal(person, me)
        in_post = Employee.objects.filter(status__in=IN_POST_STATUSES)
        context = {
            "filter_form": form,
            "page_obj": page_obj,
            "view": view,
            "query": q,
            "is_hr": permissions.can(me, "people.manage"),
            "can_import": permissions.can(me, "people.import"),
            "counts": {
                "people": in_post.count(),
                "sites": in_post.values("site").distinct().exclude(site=None).count(),
                "services": in_post.values("service").distinct().exclude(service=None).count(),
            },
            "list_url": reverse("people:list"),
            "view_options": [("liste", _("Liste"), "list"), ("cartes", _("Cartes"), "grid")],
        }
        if is_htmx(request) and request.htmx.target == "results":
            return render(request, f"{self.template_name}#results", context)
        return render(request, self.template_name, context)


@require_GET
@permission_required("people.view_list")
def suggestions(request):
    """Recherche globale : 5 collaborateurs au plus dès le premier caractère."""
    q = request.GET.get("q", "").strip()
    people = []
    if q:
        people = list(
            Employee.objects.filter(status__in=IN_POST_STATUSES)
            .filter(
                Q(first_name__icontains=q) | Q(last_name__icontains=q) | Q(job_title__icontains=q)
            )
            .select_related("service")[:5]
        )
        for person in people:
            person.photo_url = photo_url(person)
    return render(request, "people/partials/suggestions.html", {"people": people, "query": q})


# ---------- Fiche ----------

TAB_INFO, TAB_TEAM, TAB_HISTORY = "informations", "equipe", "historique"


class EmployeeDetailView(PermissionRequiredMixin, View):
    permission = "people.view_list"

    def get(self, request, public_id):
        me = request.employee
        employee = get_employee(request, public_id)
        is_hr = permissions.can(me, "people.manage")
        tabs = [(TAB_INFO, _("Informations")), (TAB_TEAM, _("Équipe"))]
        if is_hr:
            tabs.append((TAB_HISTORY, _("Historique")))
        tab = request.GET.get("onglet", TAB_INFO)
        if tab not in dict(tabs):
            tab = TAB_INFO
        url = reverse("people:detail", args=[employee.public_id])
        context = {
            "person": employee,
            "photo_url": photo_url(employee),
            "is_self": employee.pk == me.pk,
            "is_hr": is_hr,
            "can_view_hr": permissions.can(me, "people.view_hr", employee),
            "can_archive": is_hr and not services.archive_refusal(employee, me),
            "tab": tab,
            "detail_url": url,
            "tabs": [
                {"label": label, "url": f"{url}?onglet={key}", "active": key == tab}
                for key, label in tabs
            ],
        }
        if tab == TAB_TEAM:
            reports = list(
                Employee.objects.filter(
                    manager=employee, status__in=IN_POST_STATUSES
                ).select_related("site")
            )
            for person in reports:
                person.photo_url = photo_url(person)
            context["reports"] = reports
        elif tab == TAB_HISTORY:
            context["changes"] = employee.changes.select_related("actor")[:50]
        return render(request, "people/detail.html", context)


class EmployeeFormView(PermissionRequiredMixin, View):
    """Création (`public_id` absent) et modification d'une fiche, en page complète."""

    permission = "people.manage"
    template_name = "people/form.html"

    def get_employee(self, request, public_id):
        if public_id is None:
            return Employee()
        employee = get_employee(request, public_id)
        require(request, "people.manage", employee)
        return employee

    def form(self, request, employee, data=None, files=None):
        # Son propre profil n'est pas modifiable (docs/modules/04-administration.md) : sur sa
        # propre fiche, le champ n'existe pas ; update_employee le refuse aussi.
        is_self = employee.pk is not None and employee.pk == request.employee.pk
        return EmployeeForm(
            data,
            files,
            instance=employee,
            can_assign_role=permissions.can(request.employee, "people.assign_role") and not is_self,
        )

    def render_form(self, request, form, employee, status=200):
        return render(
            request,
            self.template_name,
            {
                "form": form,
                "person": employee if employee.pk else None,
                "photo_url": photo_url(employee) if employee.pk else "",
            },
            status=status,
        )

    def get(self, request, public_id=None):
        employee = self.get_employee(request, public_id)
        return self.render_form(request, self.form(request, employee), employee)

    def post(self, request, public_id=None):
        employee = self.get_employee(request, public_id)
        form = self.form(request, employee, request.POST, request.FILES)
        if not form.is_valid():
            return self.render_form(request, form, employee, status=422)
        photo = form.cleaned_data.get("photo_upload")
        try:
            if public_id is None:
                employee = services.create_employee(
                    form.model_data(), actor=request.employee, photo=photo, request=request
                )
                message = _("Fiche créée")
                if form.cleaned_data.get("invite"):
                    accounts.invite(employee, sent_by=request.employee, request=request)
                    message = _("Fiche créée, invitation envoyée")
            else:
                services.update_employee(
                    employee,
                    form.model_data(),
                    actor=request.employee,
                    photo=photo,
                    remove_photo=form.cleaned_data.get("remove_photo", False),
                    request=request,
                )
                message = _("Fiche enregistrée")
        except (services.PeopleError, accounts.InvitationError) as error:
            form.add_error(None, error.message)
            return self.render_form(request, form, employee, status=422)
        messages.success(request, message)
        return redirect("people:detail", public_id=employee.public_id)


# ---------- Archivage ----------


@require_http_methods(["GET", "POST"])
def archive(request, public_id):
    employee = get_employee(request, public_id)
    require(request, "people.manage", employee)
    url = reverse("people:archive", args=[employee.public_id])
    form = ArchiveForm(request.POST or None)
    template = "people/partials/archive_modal.html"
    if request.method == "POST":
        if not form.is_valid():
            return render(
                request,
                f"{template}#form",
                {"form": form, "person": employee, "action_url": url},
                status=422,
            )
        try:
            previous = services.archive(
                employee,
                actor=request.employee,
                departure_date=form.cleaned_data["departure_date"],
                request=request,
            )
        except services.PeopleError as error:
            form.add_error(None, error.message)
            return render(
                request,
                f"{template}#form",
                {"form": form, "person": employee, "action_url": url},
                status=422,
            )
        token = undo.make_token(
            request, "people.archive", json.dumps({"id": str(employee.public_id), **previous})
        )
        return _with_event(
            toast_response(
                Toast(
                    title=_("Fiche archivée"),
                    message=_("%(name)s est maintenant au statut Parti.")
                    % {"name": employee.full_name},
                    emphasis=employee.full_name,
                    undo_url=reverse("people:undo", args=[token]),
                ),
                close_modal=True,
            )
        )
    return render(request, template, {"form": form, "person": employee, "action_url": url})


def _with_event(response: HttpResponse) -> HttpResponse:
    """Les zones qui affichent les fiches se rechargent (liste, en-tête de fiche)."""
    return trigger(response, **{CHANGED_EVENT: True})


@require_POST
def undo_archive(request, token):
    try:
        payload = undo.read_token(request, token)
    except undo.UndoError as error:
        return toast_response(Toast(title=str(error.message), kind="err"), status=409)
    if payload.action != "people.archive":
        raise Http404
    previous = json.loads(payload.target)
    employee = get_object_or_404(Employee, public_id=previous["id"])
    require(request, "people.manage", employee)
    services.undo_archive(employee, previous, actor=request.employee, request=request)
    return _with_event(
        toast_response(
            Toast(
                title=_("Archivage annulé"),
                message=_("%(name)s est de nouveau en poste.") % {"name": employee.full_name},
                kind="info",
            )
        )
    )


@require_POST
def reactivate(request, public_id):
    employee = get_employee(request, public_id)
    require(request, "people.manage", employee)
    try:
        services.reactivate(employee, actor=request.employee, request=request)
    except services.PeopleError as error:
        return toast_response(Toast(title=str(error.message), kind="err"), status=409)
    return _with_event(
        toast_response(
            Toast(
                title=_("Fiche réactivée"),
                message=_("%(name)s est de nouveau en poste.") % {"name": employee.full_name},
            )
        )
    )


# ---------- Mes coordonnées ----------


@require_http_methods(["GET", "POST"])
def edit_contact(request):
    me = request.employee
    require(request, "people.edit_contact", me)
    template = "people/partials/contact_modal.html"
    initial = {"phone": me.phone, "office": me.office}
    form = ContactForm(request.POST or None, initial=initial)
    if request.method == "POST":
        if not form.is_valid():
            return render(request, f"{template}#form", {"form": form}, status=422)
        services.update_contact(
            me,
            phone=form.cleaned_data["phone"],
            office=form.cleaned_data["office"],
            request=request,
        )
        return _with_event(
            toast_response(Toast(title=_("Coordonnées enregistrées")), close_modal=True)
        )
    return render(request, template, {"form": form})


# ---------- Import CSV ----------

IMPORT_SESSION_KEY = "people_import"


@require_http_methods(["GET", "POST"])
@permission_required("people.import")
def import_people(request):
    step = request.POST.get("step", "upload") if request.method == "POST" else "upload"
    if step == "confirm":
        stored = request.session.get(IMPORT_SESSION_KEY) or {}
        if stored.get("token") != request.POST.get("token"):
            messages.error(request, _("Cet aperçu a expiré. Déposez à nouveau le fichier."))
            return redirect("people:import")
        try:
            count = importer.run(
                importer.rows_from_session(stored["rows"]),
                actor=request.employee,
                request=request,
            )
        except importer.ImportFileError as error:
            messages.error(request, str(error.message))
            return redirect("people:import")
        request.session.pop(IMPORT_SESSION_KEY, None)
        messages.success(request, _("%(n)s fiches importées") % {"n": count})
        return redirect("people:list")
    form = ImportUploadForm(request.POST or None, request.FILES or None)
    preview = None
    if request.method == "POST" and form.is_valid():
        try:
            preview = importer.check(importer.read(form.cleaned_data["file"]))
        except importer.ImportFileError as error:
            form.add_error("file", error.message)
        else:
            token = uuid.uuid4().hex
            request.session[IMPORT_SESSION_KEY] = {"token": token, "rows": preview.as_session()}
            return render(
                request, "people/import.html", {"form": form, "preview": preview, "token": token}
            )
    status = 422 if form.errors else 200
    return render(request, "people/import.html", {"form": form, "preview": preview}, status=status)
