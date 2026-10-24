"""Changements d'état des questionnaires : brouillon, publication, clôture, réponse.

Répondre crée le reçu et la réponse anonyme dans la même transaction, sans clé commune, et
n'écrit rien d'autre : ni journal, ni notification, ni log qui relierait une personne à ses
réponses (M-10, L6-03)."""

from dataclasses import dataclass
from datetime import date, timedelta

from django.db import IntegrityError, transaction
from django.db.models import Exists, OuterRef, QuerySet
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.core import audit, notifications
from apps.core.dates import format_date
from apps.core.errors import ServiceError
from apps.people.models import IN_POST_STATUSES, Employee, EmployeeStatus
from apps.surveys.models import (
    COMMENT_MAX,
    MAX_SCALE_QUESTIONS,
    QUESTION_MAX,
    TEXT_ANSWER_MAX,
    TITLE_MAX,
    Answer,
    Question,
    Survey,
    SurveyInvitation,
    SurveyReceipt,
    SurveyResponse,
)

NEW_HIRE_DAYS = 365
ALREADY_ANSWERED = _("Vous avez déjà répondu à ce questionnaire.")
NOT_OPEN = _("Ce questionnaire n'accepte plus de réponses.")


class SurveyError(ServiceError):
    """Refus d'une action sur un questionnaire (message affiché, champ éventuel)."""


@dataclass(frozen=True)
class DraftData:
    """Contenu d'un brouillon : questions notées (une par ligne) et question ouverte."""

    title: str
    audience: str
    due_date: date | None
    scale_questions: list[str]
    open_question: str = ""


# ---------- Public ----------


def audience_people(audience: str, today: date) -> QuerySet[Employee]:
    """Personnes visées (L6-04) : présentes (« Actif ») ; « Managers » : au moins un
    collaborateur direct ; « Arrivés depuis moins d'un an » : arrivée dans les 365 jours."""
    people = Employee.objects.filter(status=EmployeeStatus.ACTIVE)
    if audience == Survey.Audience.MANAGERS:
        reports = Employee.objects.filter(manager=OuterRef("pk"), status__in=IN_POST_STATUSES)
        return people.filter(Exists(reports))
    if audience == Survey.Audience.NEW_HIRES:
        return people.filter(
            arrival_date__gt=today - timedelta(days=NEW_HIRE_DAYS), arrival_date__lte=today
        )
    return people


def is_due_passed(survey: Survey, today: date) -> bool:
    return survey.due_date is not None and survey.due_date < today


def accepts_answers(survey: Survey, today: date) -> bool:
    return survey.status == Survey.Status.OPEN and not is_due_passed(survey, today)


# ---------- Brouillon ----------


def _check_draft(data: DraftData, today: date) -> None:
    """Contrôles du service (A3-02), refaits même si le formulaire les a déjà faits."""
    if not data.title.strip() or len(data.title) > TITLE_MAX:
        raise SurveyError(_("Donnez un titre au questionnaire."), "title")
    if data.audience not in Survey.Audience.values:
        raise SurveyError(_("Choisissez le public."), "audience")
    if data.due_date is not None and data.due_date < today:
        raise SurveyError(_("L'échéance ne peut pas être passée."), "due_date")
    if not data.scale_questions:
        raise SurveyError(_("Ajoutez au moins une question."), "questions")
    if len(data.scale_questions) > MAX_SCALE_QUESTIONS:
        raise SurveyError(_("Un questionnaire compte au plus 20 questions notées."), "questions")
    labels = [*data.scale_questions, data.open_question]
    if any(len(label) > QUESTION_MAX for label in labels):
        raise SurveyError(_("Une question dépasse 300 caractères."), "questions")


def _write_questions(survey: Survey, data: DraftData) -> None:
    survey.questions.all().delete()
    kinds = [(Question.Kind.SCALE, label) for label in data.scale_questions]
    if data.open_question:
        kinds.append((Question.Kind.TEXT, data.open_question))
    for order, (kind, label) in enumerate(kinds, start=1):
        Question.objects.create(survey=survey, order=order, kind=kind, label=label)


@transaction.atomic
def create_draft(data: DraftData, *, actor: Employee, request=None) -> Survey:
    _check_draft(data, timezone.localdate())
    survey = Survey.objects.create(
        title=data.title, audience=data.audience, due_date=data.due_date, created_by=actor
    )
    _write_questions(survey, data)
    audit.log(
        "surveys.draft_created",
        _("Questionnaire créé : %(title)s") % {"title": survey.title},
        actor=actor,
        target=survey,
        request=request,
    )
    return survey


STATE_MESSAGES = {
    Survey.Status.DRAFT: _("Ce questionnaire n'est pas encore publié."),
    Survey.Status.OPEN: _("Ce questionnaire est déjà publié."),
    Survey.Status.CLOSED: _("Ce questionnaire est déjà clos."),
}


def check_status(survey: Survey, expected: str) -> None:
    """L'action n'est possible que dans l'état `expected` ; sinon, le message dit l'état
    réel (« Ce questionnaire est déjà clos. »), jamais un « a changé » vague (L6-20)."""
    if survey.status != expected:
        raise SurveyError(STATE_MESSAGES[survey.status])


def _lock(survey: Survey, *, status: str) -> Survey:
    locked = Survey.objects.select_for_update().get(pk=survey.pk)
    check_status(locked, status)
    return locked


@transaction.atomic
def update_draft(survey: Survey, data: DraftData, *, actor: Employee, request=None) -> Survey:
    """« Modifier le brouillon » (L6-07) : titre, public, échéance et questions, tant que le
    questionnaire n'est pas publié."""
    _check_draft(data, timezone.localdate())
    survey = _lock(survey, status=Survey.Status.DRAFT)
    survey.title, survey.audience, survey.due_date = data.title, data.audience, data.due_date
    survey.save()
    _write_questions(survey, data)
    audit.log(
        "surveys.draft_updated",
        _("Brouillon modifié : %(title)s") % {"title": survey.title},
        actor=actor,
        target=survey,
        request=request,
    )
    return survey


@transaction.atomic
def delete_draft(survey: Survey, *, actor: Employee, request=None) -> None:
    survey = _lock(survey, status=Survey.Status.DRAFT)
    audit.log(
        "surveys.draft_deleted",
        _("Brouillon supprimé : %(title)s") % {"title": survey.title},
        actor=actor,
        target=survey,
        request=request,
    )
    survey.delete()


# ---------- Publication et clôture ----------


def check_publishable(survey: Survey, today: date) -> list[Employee]:
    """Brouillon, échéance à venir, public d'au moins le seuil d'anonymat (L6-05, L6-17).
    Appelé avant d'ouvrir la confirmation, puis sous verrou à la publication. Renvoie le
    public."""
    check_status(survey, Survey.Status.DRAFT)
    if is_due_passed(survey, today):
        raise SurveyError(_("L'échéance est passée : modifiez le brouillon avant de publier."))
    people = list(audience_people(survey.audience, today).select_related("user"))
    if len(people) < survey.anonymity_threshold:
        raise SurveyError(
            _(
                "Le public compte moins de %(n)s personnes : les résultats ne pourraient "
                "jamais être affichés sans risque pour l'anonymat."
            )
            % {"n": survey.anonymity_threshold}
        )
    return people


@transaction.atomic
def publish(survey: Survey, *, actor: Employee, request=None) -> int:
    """Fige le public (invitations), ouvre le questionnaire et prévient le public. Refusé si
    le public compte moins de personnes que le seuil d'anonymat (L6-05). Renvoie la taille du
    public."""
    survey = _lock(survey, status=Survey.Status.DRAFT)
    people = check_publishable(survey, timezone.localdate())
    # bulk_create ne passe pas par TenantModel.save() : l'entreprise est vérifiée ici.
    if any(person.company_id != survey.company_id for person in people):
        raise SurveyError(_("Le public contient une personne d'une autre entreprise."))
    SurveyInvitation.objects.bulk_create(
        [
            SurveyInvitation(company_id=survey.company_id, survey=survey, employee=person)
            for person in people
        ]
    )
    survey.status, survey.published_at = Survey.Status.OPEN, timezone.now()
    survey.save(update_fields=["status", "published_at", "updated_at"])
    notifications.notify_many(
        [person for person in people if person.pk != actor.pk],
        _("Nouveau questionnaire : %(title)s") % {"title": survey.title},
        url=f"/questionnaires/{survey.public_id}/",
    )
    audit.log(
        "surveys.published",
        _("Questionnaire publié : %(title)s") % {"title": survey.title},
        actor=actor,
        target=survey,
        request=request,
    )
    return len(people)


@transaction.atomic
def close(survey: Survey, *, actor: Employee | None = None, request=None) -> Survey:
    """Clôture par les RH, ou automatique le lendemain de l'échéance (sans auteur, L6-06)."""
    survey = _lock(survey, status=Survey.Status.OPEN)
    survey.status, survey.closed_at = Survey.Status.CLOSED, timezone.now()
    survey.save(update_fields=["status", "closed_at", "updated_at"])
    summary = (
        _("Questionnaire clos : %(title)s")
        if actor is not None
        else _("Questionnaire clos automatiquement (échéance passée) : %(title)s")
    )
    audit.log(
        "surveys.closed",
        summary % {"title": survey.title},
        actor=actor,
        target=survey,
        request=request,
    )
    return survey


def check_extendable(survey: Survey, today: date) -> None:
    """Prolonger n'est possible que tant que l'échéance n'est pas passée : dès que les
    résultats ont pu être visibles, plus aucune réponse ne doit entrer, sinon la différence
    entre deux consultations révélerait les réponses d'une personne (L6-01, L6-21)."""
    check_status(survey, Survey.Status.OPEN)
    if is_due_passed(survey, today):
        raise SurveyError(_("L'échéance est passée : le questionnaire ne peut plus être prolongé."))


def check_new_due_date(survey: Survey, new_date: date | None, today: date) -> None:
    check_extendable(survey, today)
    if new_date is None or new_date <= today:
        raise SurveyError(_("Choisissez une date à venir."), "due_date")
    if survey.due_date is not None and new_date <= survey.due_date:
        raise SurveyError(_("Choisissez une date après l'échéance actuelle."), "due_date")


@transaction.atomic
def extend_due_date(survey: Survey, new_date: date, *, actor: Employee, request=None) -> Survey:
    """« Prolonger l'échéance » d'un questionnaire ouvert dont l'échéance n'est pas passée,
    vers une date future (L6-21)."""
    survey = _lock(survey, status=Survey.Status.OPEN)
    check_new_due_date(survey, new_date, timezone.localdate())
    previous = survey.due_date
    survey.due_date = new_date
    survey.save(update_fields=["due_date", "updated_at"])
    audit.log(
        "surveys.due_date_extended",
        _("Échéance prolongée : %(title)s, du %(a)s au %(b)s")
        % {
            "title": survey.title,
            "a": format_date(previous, "long") if previous else "—",
            "b": format_date(new_date, "long"),
        },
        actor=actor,
        target=survey,
        request=request,
    )
    return survey


def close_expired(today: date) -> int:
    """Tâche quotidienne : clôt les questionnaires dont l'échéance est passée."""
    expired = Survey.objects.filter(status=Survey.Status.OPEN, due_date__lt=today)
    count = 0
    for survey in expired:
        try:
            close(survey)
        except SurveyError:
            continue  # clos entre-temps par les RH
        count += 1
    return count


# ---------- Réponse anonyme ----------


def _clean_answers(survey: Survey, raw: dict) -> list[tuple[Question, dict]]:
    """Note de 1 à 5 obligatoire, commentaire et réponse libre bornés (A3-02)."""
    cleaned = []
    for question in survey.questions.all():
        value = raw.get(question.pk, {})
        if question.kind == Question.Kind.SCALE:
            score = value.get("score")
            if score not in (1, 2, 3, 4, 5):
                raise SurveyError(_("Choisissez une note de 1 à 5."), f"q{question.order}")
            comment = (value.get("comment") or "").strip()
            if len(comment) > COMMENT_MAX:
                raise SurveyError(_("Le commentaire dépasse 1 000 caractères."))
            cleaned.append((question, {"score": score, "comment": comment}))
        else:
            text = (value.get("text") or "").strip()
            if len(text) > TEXT_ANSWER_MAX:
                raise SurveyError(_("La réponse dépasse 2 000 caractères."))
            cleaned.append((question, {"text": text}))
    return cleaned


@transaction.atomic
def submit_answers(survey: Survey, employee: Employee, raw: dict) -> None:
    """Enregistre une réponse anonyme. `raw` : {question_pk: {"score", "comment", "text"}}.
    Le reçu (qui a répondu) et la réponse (ce qui a été répondu) sont créés dans la même
    transaction, sans clé commune ; une seconde réponse est refusée par la contrainte
    unique du reçu, même si le formulaire est renvoyé."""
    # Verrou exclusif AVANT de lire la date : une lecture des résultats en cours (verrou
    # partagé, selectors._share_lock) passe d'abord, puis la date est relue (course à minuit).
    survey = Survey.objects.select_for_update().get(pk=survey.pk)
    if not accepts_answers(survey, timezone.localdate()):
        raise SurveyError(NOT_OPEN)
    if not SurveyInvitation.objects.filter(survey=survey, employee=employee).exists():
        raise SurveyError(_("Ce questionnaire ne vous est pas destiné."))
    answers = _clean_answers(survey, raw)
    try:
        with transaction.atomic():
            SurveyReceipt.objects.create(survey=survey, employee=employee)
    except IntegrityError as exc:
        raise SurveyError(ALREADY_ANSWERED) from exc
    response = SurveyResponse.objects.create(survey=survey)
    for question, values in answers:
        Answer.objects.create(response=response, question=question, **values)
