"""Écrans des questionnaires (docs/modules/09-questionnaires.md). Vues minces : lectures dans
selectors.py, changements d'état dans services.py. Aucun écran ne montre qui a répondu ni
qui n'a pas répondu (L6-01)."""

from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from apps.core import permissions
from apps.core.access import module_required, permission_required
from apps.core.htmx import (
    Toast,
    confirm_response,
    error_response,
    is_htmx,
    location,
    modal_form_response,
    toast_response,
)
from apps.core.models import Module
from apps.surveys import selectors, services
from apps.surveys.forms import AnswerForm, DueDateForm, FilterForm, SurveyForm
from apps.surveys.models import Survey, SurveyInvitation

PER_PAGE = 20
FORM_TEMPLATE = "surveys/partials/form_modal.html"
VIEW_RESULTS = "resultats"


def _get(request, public_id) -> Survey:
    """Brouillon : RH et administrateur seulement (403, comme le prototype). Salarié : un
    questionnaire qui ne lui est pas destiné n'existe pas pour lui (404)."""
    survey = get_object_or_404(Survey.objects.select_related("created_by"), public_id=public_id)
    me = request.employee
    if permissions.can(me, "surveys.manage"):
        return survey
    if survey.status == Survey.Status.DRAFT:
        raise PermissionDenied
    invited = SurveyInvitation.objects.filter(survey=survey, employee=me).exists()
    if not invited and not permissions.can(me, "surveys.view_results"):
        raise Http404
    return survey


def _url(survey: Survey) -> str:
    return reverse("surveys:detail", args=[survey.public_id])


@require_GET
@module_required(Module.SURVEYS)
@permission_required("surveys.answer")
def survey_list(request):
    me = request.employee
    can_manage = permissions.can(me, "surveys.manage")
    filters = FilterForm(request.GET or None, can_manage=can_manage)
    cleaned = filters.cleaned_data if filters.is_valid() else {}
    q, status = cleaned.get("q", "").strip(), cleaned.get("statut", "")
    rows = selectors.survey_list(me, timezone.localdate(), q=q, status=status).order_by(
        "-created_at", "-pk"
    )
    context = {
        "filter_form": filters,
        "page_obj": Paginator(rows, PER_PAGE).get_page(request.GET.get("page")),
        "todo": selectors.to_answer(me, timezone.localdate()),
        "can_manage": can_manage,
        "can_view_results": permissions.can(me, "surveys.view_results"),
        "list_url": reverse("surveys:list"),
        "filtered": bool(q or status),
    }
    if is_htmx(request) and request.htmx.target == "results":
        return render(request, "surveys/list.html#results", context)
    return render(request, "surveys/list.html", context)


def _results_context(survey: Survey, today) -> dict:
    responses, invited = selectors.participation(survey)
    return {
        "results": selectors.survey_results(survey, today),
        "responses": responses,
        "invited": invited,
        "finished": survey.status == Survey.Status.CLOSED or services.is_due_passed(survey, today),
    }


@require_GET
@module_required(Module.SURVEYS)
@permission_required("surveys.answer")
def survey_detail(request, public_id):
    return _render_detail(request, _get(request, public_id))


def _render_detail(request, survey: Survey, form: AnswerForm | None = None):
    """Selon le cas : répondre, résultats, aperçu du brouillon, ou merci et clos."""
    me = request.employee
    today = timezone.localdate()
    can_answer = selectors.can_answer(survey, me, today)
    can_view_results = permissions.can(me, "surveys.view_results")
    wants_results = request.GET.get("vue") == VIEW_RESULTS
    if wants_results and not can_view_results:
        raise PermissionDenied
    if survey.status == Survey.Status.DRAFT:
        mode = "draft"
    elif can_answer and not wants_results:
        mode = "answer"
    elif can_view_results:
        mode = "results"
    else:
        mode = "done"
    context = {
        "survey": survey,
        "questions": list(survey.questions.all()),
        "mode": mode,
        "can_manage": permissions.can(me, "surveys.manage"),
        "both": can_answer and can_view_results,
        "has_answered": survey.receipts.filter(employee=me).exists(),
        "form": form
        or (AnswerForm(questions=survey.questions.all()) if mode == "answer" else None),
        "view_results": VIEW_RESULTS,
    }
    if mode == "results":
        context.update(_results_context(survey, today))
    return render(request, "surveys/detail.html", context, status=422 if form else 200)


@require_POST
@module_required(Module.SURVEYS)
@permission_required("surveys.answer")
def survey_answer(request, public_id):
    survey = _get(request, public_id)
    form = AnswerForm(request.POST, questions=survey.questions.all())
    if not form.is_valid():
        return _render_detail(request, survey, form)
    try:
        services.submit_answers(survey, request.employee, form.answers())
    except services.SurveyError as error:
        if error.field in form.fields:
            form.add_error(error.field, error.message)
            return _render_detail(request, survey, form)
        return error_response(error, close_modal=True)
    toast = Toast(title=_("Réponses envoyées"), message=_("Merci. Vos réponses sont anonymes."))
    return location(toast_response(toast), _url(survey))


def _form_response(request, form, *, action_url, survey=None):
    context = {"form": form, "action_url": action_url, "survey": survey}
    return modal_form_response(request, FORM_TEMPLATE, context)


def _save_draft(request, form, *, action_url, survey=None):
    """Création ou modification d'un brouillon, puis affichage de sa page."""
    if request.method == "GET" or not form.is_valid():
        return _form_response(request, form, action_url=action_url, survey=survey)
    try:
        if survey is None:
            survey = services.create_draft(
                form.draft_data(), actor=request.employee, request=request
            )
            title = _("Brouillon créé")
        else:
            services.update_draft(
                survey, form.draft_data(), actor=request.employee, request=request
            )
            title = _("Brouillon modifié")
    except services.SurveyError as error:
        form.add_error(error.field if error.field in form.fields else None, error.message)
        return _form_response(request, form, action_url=action_url, survey=survey)
    return location(toast_response(Toast(title=title), close_modal=True), _url(survey))


@require_http_methods(["GET", "POST"])
@module_required(Module.SURVEYS)
@permission_required("surveys.manage")
def survey_new(request):
    form = SurveyForm(request.POST or None)
    return _save_draft(request, form, action_url=reverse("surveys:new"))


@require_http_methods(["GET", "POST"])
@module_required(Module.SURVEYS)
@permission_required("surveys.manage")
def survey_edit(request, public_id):
    survey = _get(request, public_id)
    if request.method == "GET" and survey.status != Survey.Status.DRAFT:
        return error_response(services.SurveyError(services.STATE_MESSAGES[survey.status]))
    form = SurveyForm(request.POST or None, initial=SurveyForm.initial_for(survey))
    action_url = reverse("surveys:edit", args=[survey.public_id])
    return _save_draft(request, form, action_url=action_url, survey=survey)


def _confirm(request, survey, *, action, **texts):
    action_url = reverse(f"surveys:{action}", args=[survey.public_id])
    return confirm_response(request, action_url=action_url, **texts)


@require_http_methods(["GET", "POST"])
@module_required(Module.SURVEYS)
@permission_required("surveys.manage")
def survey_publish(request, public_id):
    survey = _get(request, public_id)
    if request.method == "GET":
        try:
            services.check_publishable(survey, timezone.localdate())
        except services.SurveyError as error:
            return error_response(error)
        return _confirm(
            request,
            survey,
            title=_("Publier ce questionnaire ?"),
            text=_(
                "Il sera proposé à : %(audience)s. Une fois publié, les questions ne sont plus "
                "modifiables."
            )
            % {"audience": survey.get_audience_display()},
            ok_label=_("Publier"),
            action="publish",
        )
    try:
        size = services.publish(survey, actor=request.employee, request=request)
    except services.SurveyError as error:
        return error_response(error, close_modal=True)
    toast = Toast(
        title=_("Questionnaire publié"),
        message=_("%(n)s personnes sont notifiées.") % {"n": size},
    )
    return location(toast_response(toast, close_modal=True), _url(survey))


@require_http_methods(["GET", "POST"])
@module_required(Module.SURVEYS)
@permission_required("surveys.manage")
def survey_close(request, public_id):
    survey = _get(request, public_id)
    if request.method == "GET":
        try:
            services.check_status(survey, Survey.Status.OPEN)
        except services.SurveyError as error:
            return error_response(error)
        responses, _invited = selectors.participation(survey)
        return _confirm(
            request,
            survey,
            title=_("Clore ce questionnaire ?"),
            text=_("Il n'acceptera plus de réponses (%(n)s reçues).") % {"n": responses},
            ok_label=_("Clore"),
            action="close",
        )
    try:
        services.close(survey, actor=request.employee, request=request)
    except services.SurveyError as error:
        return error_response(error, close_modal=True)
    return location(
        toast_response(Toast(title=_("Questionnaire clos")), close_modal=True), _url(survey)
    )


@require_http_methods(["GET", "POST"])
@module_required(Module.SURVEYS)
@permission_required("surveys.manage")
def survey_delete(request, public_id):
    survey = _get(request, public_id)
    if request.method == "GET":
        try:
            services.check_status(survey, Survey.Status.DRAFT)
        except services.SurveyError as error:
            return error_response(error)
        return _confirm(
            request,
            survey,
            title=_("Supprimer ce brouillon ?"),
            text=_("« %(title)s » sera définitivement supprimé.") % {"title": survey.title},
            ok_label=_("Supprimer"),
            action="delete",
            danger=True,
        )
    try:
        services.delete_draft(survey, actor=request.employee, request=request)
    except services.SurveyError as error:
        return error_response(error, close_modal=True)
    toast = toast_response(Toast(title=_("Brouillon supprimé")), close_modal=True)
    return location(toast, reverse("surveys:list"))


@require_http_methods(["GET", "POST"])
@module_required(Module.SURVEYS)
@permission_required("surveys.manage")
def survey_extend(request, public_id):
    """« Prolonger l'échéance » d'un questionnaire ouvert (L6-21)."""
    survey = _get(request, public_id)
    try:
        services.check_status(survey, Survey.Status.OPEN)
    except services.SurveyError as error:
        return error_response(error, close_modal=request.method == "POST")
    form = DueDateForm(request.POST or None, initial={"due_date": survey.due_date})
    context = {
        "form": form,
        "survey": survey,
        "action_url": reverse("surveys:extend", args=[survey.public_id]),
    }
    if request.method == "GET" or not form.is_valid():
        return modal_form_response(request, "surveys/partials/extend_modal.html", context)
    try:
        services.extend_due_date(
            survey, form.cleaned_data["due_date"], actor=request.employee, request=request
        )
    except services.SurveyError as error:
        form.add_error(error.field, error.message)
        return modal_form_response(request, "surveys/partials/extend_modal.html", context)
    toast = Toast(title=_("Échéance prolongée"), message=survey.title)
    return location(toast_response(toast, close_modal=True), _url(survey))


@require_GET
@module_required(Module.SURVEYS)
@permission_required("surveys.view_results")
def survey_more_answers(request, public_id, order):
    """« Afficher plus » sous une question : suite des commentaires ou réponses libres,
    seulement si les résultats sont visibles (même règle que la page de résultats)."""
    survey = _get(request, public_id)
    start = max(_int(request.GET.get("debut")), 0)
    found = selectors.more_written_answers(survey, order, start, timezone.localdate())
    if found is None:
        raise Http404
    question, rows, total = found
    following = start + len(rows)
    return render(
        request,
        "surveys/partials/more_answers.html",
        {
            "survey": survey,
            "question": question,
            "rows": rows,
            "next_start": following if following < total else None,
            "remaining": total - following,
        },
    )


def _int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
