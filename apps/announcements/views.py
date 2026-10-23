"""Écrans de la communication interne (docs/modules/08-annonces.md). Vues minces : les
lectures sont dans selectors.py, les changements d'état dans services.py."""

from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from apps.announcements import selectors, services
from apps.announcements.forms import AnnouncementForm, FilterForm
from apps.announcements.models import Announcement
from apps.core import permissions, undo
from apps.core.access import module_required, permission_required, require
from apps.core.htmx import (
    Toast,
    confirm_response,
    error_response,
    is_htmx,
    location,
    modal_form_response,
    toast_response,
    trigger,
)
from apps.core.models import Module

CHANGED = "announcementsChanged"
PER_PAGE = 20
FORM_TEMPLATE = "announcements/partials/form_modal.html"


def _get(public_id) -> Announcement:
    announcement = selectors.visible().select_related("author").filter(public_id=public_id).first()
    if announcement is None:
        raise Http404(services.GONE)
    return announcement


def _detail_url(announcement: Announcement) -> str:
    return reverse("announcements:detail", args=[announcement.public_id])


@require_GET
@module_required(Module.ANNOUNCEMENTS)
@permission_required("announcements.read")
def announcement_list(request):
    me = request.employee
    filters = FilterForm(request.GET or None)
    filters.is_valid()
    q = filters.cleaned_data.get("q", "").strip() if filters.is_bound else ""
    category = filters.cleaned_data.get("categorie", "") if filters.is_bound else ""
    rows = selectors.announcement_list(me, q=q, category=category)
    context = {
        "filter_form": filters,
        "page_obj": Paginator(rows, PER_PAGE).get_page(request.GET.get("page")),
        "unread": selectors.unread_count(me),
        "can_manage": permissions.can(me, "announcements.manage"),
        "list_url": reverse("announcements:list"),
        "filtered": bool(q or category),
    }
    if is_htmx(request) and request.htmx.target == "results":
        return render(request, "announcements/list.html#results", context)
    return render(request, "announcements/list.html", context)


@require_GET
@module_required(Module.ANNOUNCEMENTS)
@permission_required("announcements.read")
def announcement_detail(request, public_id):
    me = request.employee
    try:
        announcement = _get(public_id)
    except Http404:
        return render(request, "announcements/gone.html", status=404)
    services.mark_read(announcement, me)
    context = {
        "announcement": announcement,
        "can_manage": permissions.can(me, "announcements.manage"),
        "reads": selectors.read_stats(announcement)
        if services.can_see_reads(me, announcement)
        else None,
    }
    return render(request, "announcements/detail.html", context)


def _form_response(request, form, *, action_url, announcement=None):
    context = {"form": form, "action_url": action_url, "announcement": announcement}
    return modal_form_response(request, FORM_TEMPLATE, context)


@require_http_methods(["GET", "POST"])
@module_required(Module.ANNOUNCEMENTS)
@permission_required("announcements.manage")
def announcement_new(request):
    form = AnnouncementForm(request.POST or None)
    action_url = reverse("announcements:new")
    if request.method == "GET" or not form.is_valid():
        return _form_response(request, form, action_url=action_url)
    try:
        announcement = services.publish(form.cleaned_data, actor=request.employee, request=request)
    except services.AnnouncementError as error:
        form.add_error(error.field, error.message)
        return _form_response(request, form, action_url=action_url)
    toast = Toast(
        title=_("Annonce publiée"), message=_("Tous les salariés présents sont notifiés.")
    )
    return location(toast_response(toast, close_modal=True), _detail_url(announcement))


@require_http_methods(["GET", "POST"])
@module_required(Module.ANNOUNCEMENTS)
@permission_required("announcements.manage")
def announcement_edit(request, public_id):
    announcement = _get(public_id)
    initial = {name: getattr(announcement, name) for name in services.EDITABLE_FIELDS}
    form = AnnouncementForm(request.POST or None, initial=initial)
    action_url = reverse("announcements:edit", args=[announcement.public_id])
    if request.method == "GET" or not form.is_valid():
        return _form_response(request, form, action_url=action_url, announcement=announcement)
    try:
        services.update(announcement, form.cleaned_data, actor=request.employee, request=request)
    except services.AnnouncementError as error:
        form.add_error(error.field, error.message)
        return _form_response(request, form, action_url=action_url, announcement=announcement)
    toast = toast_response(Toast(title=_("Annonce modifiée")), close_modal=True)
    return location(toast, _detail_url(announcement))


@require_POST
@module_required(Module.ANNOUNCEMENTS)
@permission_required("announcements.manage")
def announcement_pin(request, public_id):
    try:
        announcement = services.toggle_pin(_get(public_id), actor=request.employee, request=request)
    except services.AnnouncementError as error:
        return error_response(error)
    title = _("Annonce épinglée") if announcement.pinned else _("Annonce désépinglée")
    return location(toast_response(Toast(title=title)), _detail_url(announcement))


@require_http_methods(["GET", "POST"])
@module_required(Module.ANNOUNCEMENTS)
@permission_required("announcements.manage")
def announcement_delete(request, public_id):
    announcement = _get(public_id)
    if request.method == "GET":
        return confirm_response(
            request,
            title=_("Supprimer cette annonce ?"),
            text=_("« %(title)s » disparaîtra pour tous les salariés.")
            % {"title": announcement.title},
            ok_label=_("Supprimer"),
            action_url=reverse("announcements:delete", args=[announcement.public_id]),
            danger=True,
        )
    try:
        services.delete(announcement, actor=request.employee, request=request)
    except services.AnnouncementError as error:
        return error_response(error)
    token = undo.make_token(request, "announcements.delete", str(announcement.public_id))
    toast = Toast(
        title=_("Annonce supprimée"),
        message=_("« %(title)s » n'est plus visible.") % {"title": announcement.title},
        undo_url=reverse("announcements:undo", args=[token]),
    )
    return location(toast_response(toast, close_modal=True), reverse("announcements:list"))


@require_POST
@module_required(Module.ANNOUNCEMENTS)
def undo_delete(request, token):
    """« Annuler » dans la notification visuelle : 30 s, auteur seulement (L0-03)."""
    require(request, "announcements.manage")
    try:
        data = undo.read_token(request, token)
    except undo.UndoError as error:
        return toast_response(Toast(title=str(error.message), kind="err"), status=409)
    if data.action != "announcements.delete":
        raise Http404
    try:
        announcement = services.restore(data.target, actor=request.employee, request=request)
    except services.AnnouncementError as error:
        return error_response(error)
    toast = Toast(title=_("Suppression annulée"), message=announcement.title, kind="info")
    return trigger(toast_response(toast), **{CHANGED: True})
