"""Écrans de la carrière (`/carriere/`, docs/modules/10-carriere.md).

Un entretien hors du périmètre de la personne (un collègue pour un salarié) renvoie 404. Chaque
étape est un formulaire de la page de l'entretien, envoyé par HTMX : erreurs sur place (422),
puis rechargement de la page (R1-02). Les contrôles d'étape et de personne sont dans les
services."""

from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from apps.careers import forms, selectors, services
from apps.careers.models import Review, ReviewKind, ReviewStep
from apps.core import permissions, repeatable, undo
from apps.core.access import module_required, require
from apps.core.context import ActionContext
from apps.core.dates import day_stamp
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
from apps.core.models import Module, Site
from apps.core.pdf import pdf_response
from apps.people.models import Employee

CHANGED = "careersChanged"
PER_PAGE = 8
TAB_REVIEWS, TAB_FILES = "entretiens", "fiches"
DETAIL = "careers/detail.html"
module_view = module_required(Module.CAREERS)


def _review(request, public_id) -> Review:
    """Entretien du périmètre de la personne, sinon 404 (jamais 403 : on ne révèle pas son
    existence)."""
    return get_object_or_404(selectors.visible_reviews(request.employee), public_id=public_id)


def _employee(request, public_id) -> Employee:
    employee = get_object_or_404(Employee, public_id=public_id)
    if not selectors.can_view_file(request.employee, employee):
        raise Http404
    return employee


# ---------- Liste ----------


def _tabs(me, count: int) -> list[tuple[str, str, int]]:
    tabs = [(TAB_REVIEWS, _("Entretiens"), count)]
    if _sees_others(me):
        tabs.append((TAB_FILES, _("Fiches de suivi"), 0))
    return tabs


def _sees_others(me) -> bool:
    """Manager (équipe), RH et administrateur : onglet « Fiches de suivi »."""
    return me.has_reports or permissions.scope(me, "careers.view") == permissions.ALL


def _review_rows(me, request) -> tuple[list[Review], bool]:
    q = request.GET.get("q", "").strip()
    kind, progress = request.GET.get("type", ""), request.GET.get("avancement", "")
    rows = selectors.filter_reviews(
        me, selectors.visible_reviews(me), q=q, kind=kind, progress=progress
    )
    for row in rows:
        row.todo = selectors.is_todo(me, row)
    return rows, bool(q or kind or progress)


def _file_rows(me, request) -> tuple[list[Employee], bool]:
    q = request.GET.get("q", "").strip()
    return list(selectors.follow_up_people(me, q)), bool(q)


@require_GET
@module_view
def home(request):
    me = request.employee
    visible = selectors.visible_reviews(me)
    tabs = _tabs(me, visible.count())
    tab = request.GET.get("onglet", TAB_REVIEWS)
    if tab not in {key for key, _label, _n in tabs}:
        tab = TAB_REVIEWS
    rows, filtered = _file_rows(me, request) if tab == TAB_FILES else _review_rows(me, request)
    page_obj = Paginator(rows, PER_PAGE).get_page(request.GET.get("page"))
    if tab == TAB_FILES:
        for person in page_obj.object_list:
            notes = selectors.visible_notes(me, person)
            person.note_count, person.last_note = notes.count(), notes.first()
    url = reverse("careers:home")
    campaign = selectors.current_campaign()
    form_class = forms.FollowUpFilterForm if tab == TAB_FILES else forms.ReviewFilterForm
    context = {
        "tab": tab,
        "tabs": [
            {"label": label, "url": f"{url}?onglet={key}", "count": n, "active": key == tab}
            for key, label, n in tabs
        ],
        "page_obj": page_obj,
        "filtered": filtered,
        "has_reviews": visible.exists(),
        "filter_form": form_class(request.GET, tab=tab),
        "list_url": url,
        "campaign": campaign,
        "campaign_progress": selectors.campaign_progress(me, campaign) if campaign else None,
        "todo_count": len(selectors.todo_reviews(me)),
        "planned": selectors.planned_meetings(me),
        "can_launch": permissions.can(me, "careers.launch"),
        "can_manage_campaigns": permissions.can(me, "careers.manage_campaigns"),
        "own_file": not _sees_others(me),
    }
    if is_htmx(request) and request.htmx.target == "results":
        return render(request, "careers/home.html#results", context)
    return render(request, "careers/home.html", context)


# ---------- Lancement et campagne ----------


@require_http_methods(["GET", "POST"])
@module_view
def launch(request):
    me = require(request, "careers.launch")
    form = forms.LaunchForm(request.POST or None, viewer=me)
    template = "careers/partials/launch_modal.html"
    context = {"form": form, "action_url": reverse("careers:launch")}
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        try:
            review = services.launch_review(
                data["employee"], data["kind"], data["reason"], context=ActionContext.of(request)
            )
        except services.CareerError as error:
            form.add_error(error.field, error.message)
        else:
            return _launched(request, review)
    return modal_form_response(request, template, context)


def _launched(request, review: Review):
    token = undo.make_token(request, "careers.launch", str(review.public_id))
    name = review.employee.full_name
    toast = Toast(
        title=_("Entretien lancé"),
        message=_("%(name)s a reçu une notification dans Dianna.") % {"name": name},
        emphasis=name,
        action_label=_("Voir l'entretien"),
        action_url=services.review_url(review),
        undo_url=reverse("careers:undo", args=[token]),
    )
    return after_action(request, toast, refresh=CHANGED, close_modal=True)


def _undo_launch(request, payload) -> Toast:
    services.undo_launch(payload.target, context=ActionContext.of(request))
    return Toast(title=_("Lancement annulé"), message=_("L'entretien a été retiré."), kind="info")


def _undo_note(request, payload) -> Toast:
    services.undo_note(int(payload.target), context=ActionContext.of(request))
    return Toast(title=_("Note retirée"), kind="info")


undo.register("careers.launch", _undo_launch, refresh=CHANGED)
undo.register("careers.note", _undo_note, refresh=PAGE_CHANGED)


@require_http_methods(["GET", "POST"])
@module_view
def campaign(request):
    require(request, "careers.manage_campaigns")
    current = selectors.current_campaign()
    initial = (
        {"label": current.label, "start": current.start, "end": current.end} if current else None
    )
    form = forms.CampaignForm(request.POST or None, initial=initial)
    template = "careers/partials/campaign_modal.html"
    context = {"form": form, "campaign": current, "action_url": reverse("careers:campaign")}
    if request.method == "POST" and form.is_valid():
        try:
            saved = services.save_campaign(
                form.cleaned_data, campaign=current, context=ActionContext.of(request)
            )
        except services.CareerError as error:
            form.add_error(error.field, error.message)
        else:
            toast = Toast(title=_("Campagne enregistrée"), message=saved.label)
            return after_action(request, toast, refresh=PAGE_CHANGED, close_modal=True)
    return modal_form_response(request, template, context)


# ---------- Entretien ----------


PANEL_FORMS = {
    "self": lambda review, data, me: forms.SelfForm(data, review=review),
    "evaluation": lambda review, data, me: forms.EvaluationForm(
        data, competencies=selectors.active_competencies()
    ),
    "meeting": lambda review, data, me: forms.MeetingForm(
        data,
        initial={"meeting_date": review.meeting_date, "place": review.meeting_place},
    ),
    "report": lambda review, data, me: forms.ParcoursReportForm(
        data, review=review, initial=_report_initial(review)
    ),
}


def _report_initial(review: Review) -> dict:
    review_due, summary_due = selectors.suggested_dues(review.employee)
    if review.meeting_date:
        interval = review.employee.company.career_review_interval_years
        review_due = selectors.add_years(review.meeting_date, interval)
    return {"next_review_due": review_due, "next_summary_due": summary_due}


def _panel(me, review: Review) -> str:
    """Ce que la personne voit dans la zone de l'étape : un formulaire, la signature,
    l'attente ou la clôture."""
    if review.is_closed:
        return "closed"
    manager_side = selectors.can_act_as_manager(me, review)
    if review.step == ReviewStep.SELF and me.pk == review.employee_id:
        return "self"
    if review.step == ReviewStep.MANAGER and manager_side:
        return "evaluation" if review.kind == ReviewKind.INDIVIDUAL else "report"
    if review.step == ReviewStep.MEETING and manager_side:
        return "meeting"
    if review.step == ReviewStep.SIGNATURE and _can_sign(me, review):
        return "sign"
    return "waiting"


def _can_sign(me, review: Review) -> bool:
    if me.pk == review.employee_id:
        return review.employee_signed_at is None
    return review.manager_signed_at is None and selectors.can_act_as_manager(me, review)


def _waiting_label(review: Review) -> str:
    """« En attente de … » : les personnes attendues ; « les RH » quand elles tiennent le rôle
    du manager (sans lister chaque RH)."""
    hr_side = selectors.acting_manager(review) is None and review.step != ReviewStep.SELF
    names = [
        p.full_name
        for p in selectors.expected_actors(review)
        if not hr_side or p.pk == review.employee_id
    ]
    if hr_side:
        names.append(str(_("les RH")))
    return str(_(" et ")).join(names)


def _detail_context(request, review: Review, form=None) -> dict:
    me = request.employee
    panel = _panel(me, review)
    if form is None and panel in PANEL_FORMS:
        form = PANEL_FORMS[panel](review, None, me)
    steps = [
        {
            "label": review.step_label(step),
            "state": "done"
            if i < review.step_index
            else ("current" if i == review.step_index else "todo"),
        }
        for i, step in enumerate(review.steps)
    ]
    replaced = selectors.replaced_manager(me, review) if panel != "waiting" else None
    return {
        "review": review,
        "panel": panel,
        "form": form,
        "objectives": forms.objectives_formset(review=review) if panel == "evaluation" else None,
        "objectives_block": repeatable.BLOCKS["careers-objectives"],
        "steps": steps,
        "replaced": replaced,
        "waiting_label": _waiting_label(review) if panel == "waiting" else "",
        "can_remind": panel == "waiting"
        and me.pk != review.employee_id
        and permissions.can(me, "careers.evaluate", review),
        "ratings": review.ratings.select_related("competency"),
        "acting_manager": selectors.acting_manager(review),
        "today": timezone.localdate(),
        "places": Site.objects.order_by("name").values_list("name", flat=True),
        "file_url": reverse("careers:file", args=[review.employee.public_id]),
    }


@require_GET
@module_view
def detail(request, public_id):
    review = _review(request, public_id)
    return render(request, DETAIL, _detail_context(request, review))


def _step_done(request, title: str, message: str = ""):
    return after_action(request, Toast(title=title, message=message), refresh=PAGE_CHANGED)


def _step_error(request, review: Review, form, error):
    form.add_error(error.field if error.field in form.fields else None, error.message)
    return form_error_response(request, DETAIL, _detail_context(request, review, form))


@require_POST
@module_view
def submit_self(request, public_id):
    review = _review(request, public_id)
    form = forms.SelfForm(request.POST, review=review)
    if not form.is_valid():
        return form_error_response(request, DETAIL, _detail_context(request, review, form))
    try:
        services.submit_self(
            review,
            summary=form.cleaned_data["summary"],
            project=form.cleaned_data.get("project", ""),
            context=ActionContext.of(request),
        )
    except services.CareerError as error:
        return _step_error(request, review, form, error)
    return _step_done(request, _("Envoyé à votre manager"))


@require_POST
@module_view
def evaluate(request, public_id):
    review = _review(request, public_id)
    form = forms.EvaluationForm(request.POST, competencies=selectors.active_competencies())
    objectives = forms.objectives_formset(request.POST)
    if not (form.is_valid() and objectives.is_valid()):
        return _evaluation_error(request, review, form, objectives)
    evaluation = services.Evaluation(
        summary=form.cleaned_data["summary"],
        strengths=form.cleaned_data["strengths"],
        improvements=form.cleaned_data["improvements"],
        ratings=form.ratings(),
        objectives=[
            (f.cleaned_data["title"], f.cleaned_data["due_date"]) for f in objectives.kept()
        ],
    )
    try:
        services.submit_evaluation(review, evaluation, context=ActionContext.of(request))
    except services.CareerError as error:
        form.add_error(error.field if error.field in form.fields else None, error.message)
        return _evaluation_error(request, review, form, objectives)
    return _step_done(
        request, _("Évaluation enregistrée"), _("Prochaine étape : planifier l'entretien.")
    )


def _evaluation_error(request, review: Review, form, objectives):
    """Évaluation refusée : le formulaire et les objectifs saisis reviennent tels quels."""
    context = _detail_context(request, review, form)
    context["objectives"] = objectives
    return form_error_response(request, DETAIL, context)


@require_POST
@module_view
def plan(request, public_id):
    review = _review(request, public_id)
    form = forms.MeetingForm(request.POST)
    if not form.is_valid():
        return form_error_response(request, DETAIL, _detail_context(request, review, form))
    try:
        services.plan_meeting(
            review,
            meeting_date=form.cleaned_data["meeting_date"],
            place=form.cleaned_data["place"],
            context=ActionContext.of(request),
        )
    except services.CareerError as error:
        return _step_error(request, review, form, error)
    return _step_done(request, _("Entretien planifié"))


@require_http_methods(["GET", "POST"])
@module_view
def held(request, public_id):
    review = _review(request, public_id)
    if request.method == "GET":
        return confirm_response(
            request,
            title=_("Marquer l'entretien comme réalisé ?"),
            text=_("L'étape passe à la suite du parcours."),
            ok_label=_("Oui, il a eu lieu"),
            action_url=reverse("careers:held", args=[review.public_id]),
        )
    try:
        services.mark_held(review, context=ActionContext.of(request))
    except services.CareerError as error:
        return error_response(error, close_modal=True, refresh=PAGE_CHANGED)
    return after_action(
        request,
        Toast(title=_("Entretien marqué comme réalisé")),
        refresh=PAGE_CHANGED,
        close_modal=True,
    )


@require_POST
@module_view
def report(request, public_id):
    review = _review(request, public_id)
    form = forms.ParcoursReportForm(request.POST, review=review)
    if not form.is_valid():
        return form_error_response(request, DETAIL, _detail_context(request, review, form))
    data = services.ParcoursReport(
        report=form.cleaned_data["report"],
        trainings=form.cleaned_data["trainings"],
        next_review_due=form.cleaned_data["next_review_due"],
        next_summary_due=form.cleaned_data["next_summary_due"],
        summary_criteria=form.criteria(),
    )
    try:
        services.submit_report(review, data, context=ActionContext.of(request))
    except services.CareerError as error:
        return _step_error(request, review, form, error)
    return _step_done(request, _("Compte rendu enregistré"))


@require_http_methods(["GET", "POST"])
@module_view
def sign(request, public_id):
    review = _review(request, public_id)
    me = request.employee
    is_employee = me.pk == review.employee_id
    # Côté manager, l'envoi ne porte aucun champ : le formulaire est lié dès qu'il y a un POST.
    form = forms.SignForm(request.POST if request.method == "POST" else None)
    template = "careers/partials/sign_modal.html"
    context = {
        "form": form if is_employee else None,
        "review": review,
        "replaced": None if is_employee else selectors.replaced_manager(me, review),
        "acting_manager": selectors.acting_manager(review),
        "action_url": reverse("careers:sign", args=[review.public_id]),
    }
    if request.method == "POST" and form.is_valid():
        try:
            signed = services.sign(
                review, comment=form.cleaned_data["comment"], context=ActionContext.of(request)
            )
        except services.CareerError as error:
            return error_response(error, close_modal=True, refresh=PAGE_CHANGED)
        title = _("Entretien clos") if signed.is_closed else _("Signature enregistrée")
        message = _("Les deux signatures sont enregistrées.") if signed.is_closed else ""
        return after_action(
            request, Toast(title=title, message=message), refresh=PAGE_CHANGED, close_modal=True
        )
    return modal_form_response(request, template, context)


@require_POST
@module_view
def remind(request, public_id):
    review = _review(request, public_id)
    try:
        services.remind(review, context=ActionContext.of(request))
    except services.CareerError as error:
        return error_response(error)
    return after_action(request, Toast(title=_("Relance envoyée")))


# ---------- Fiche de suivi ----------


@require_GET
@module_view
def follow_up_file(request, public_id):
    me = request.employee
    employee = _employee(request, public_id)
    review_due, summary_due = selectors.suggested_dues(employee)
    context = {
        "employee": employee,
        "notes": selectors.visible_notes(me, employee),
        "can_add": permissions.can(me, "careers.add_note", employee),
        "last_review": selectors.last_individual_review(employee),
        "trainings": selectors.trainings_of(employee),
        "review_due": review_due,
        "summary_due": summary_due,
        "is_self": me.pk == employee.pk,
    }
    return render(request, "careers/file.html", context)


@require_http_methods(["GET", "POST"])
@module_view
def add_note(request, public_id):
    me = request.employee
    employee = _employee(request, public_id)
    require(request, "careers.add_note", employee)
    form = forms.NoteForm(request.POST or None, own_file=me.pk == employee.pk)
    template = "careers/partials/note_modal.html"
    context = {
        "form": form,
        "employee": employee,
        "action_url": reverse("careers:note", args=[employee.public_id]),
    }
    if request.method == "POST" and form.is_valid():
        try:
            note = services.add_note(
                employee,
                kind=form.cleaned_data["kind"],
                text=form.cleaned_data["text"],
                is_private=form.cleaned_data.get("is_private", False),
                context=ActionContext.of(request),
            )
        except services.CareerError as error:
            form.add_error(error.field, error.message)
        else:
            token = undo.make_token(request, "careers.note", str(note.pk))
            toast = Toast(title=_("Note ajoutée"), undo_url=reverse("careers:undo", args=[token]))
            return after_action(request, toast, refresh=PAGE_CHANGED, close_modal=True)
    return modal_form_response(request, template, context)


# ---------- Exports PDF (mêmes limites et même récupérateur que le planning) ----------


@require_GET
@module_view
def review_pdf(request, public_id):
    review = _review(request, public_id)
    context = {
        "review": review,
        "ratings": review.ratings.select_related("competency"),
        "acting_manager": selectors.acting_manager(review),
        "company": request.company,
    }
    response = pdf_response(
        request,
        "careers/pdf_review.html",
        context,
        filename=f"entretien-{day_stamp(timezone.localdate())}.pdf",
        back_url=services.review_url(review),
    )
    if response.status_code == 200:
        services.log_review_export(review, context=ActionContext.of(request))
    return response


@require_GET
@module_view
def file_pdf(request, public_id):
    employee = _employee(request, public_id)
    review_due, summary_due = selectors.suggested_dues(employee)
    context = {
        "employee": employee,
        # Jamais de note privée dans un PDF, même celles de l'auteur (Q4).
        "notes": selectors.public_notes(employee),
        "trainings": selectors.trainings_of(employee),
        "last_review": selectors.last_individual_review(employee),
        "review_due": review_due,
        "summary_due": summary_due,
        "company": request.company,
    }
    response = pdf_response(
        request,
        "careers/pdf_file.html",
        context,
        filename=f"fiche-de-suivi-{day_stamp(timezone.localdate())}.pdf",
        back_url=reverse("careers:file", args=[employee.public_id]),
    )
    if response.status_code == 200:
        services.log_file_export(employee, context=ActionContext.of(request))
    return response
