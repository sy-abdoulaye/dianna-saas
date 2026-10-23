"""Lectures des questionnaires : liste, questionnaires à remplir, résultats.

`results_visible` est la seule règle d'affichage des résultats (L6-01, L6-05) : résultats,
commentaires, réponses libres et tout futur filtre ou export passent par `survey_results`,
qui renvoie None tant que la règle n'est pas remplie. Aucune lecture ne donne la liste des
répondants ni des non-répondants."""

from dataclasses import dataclass, field
from datetime import date

from django.db.models import Count, Exists, IntegerField, OuterRef, Q, QuerySet, Subquery
from django.db.models.functions import Coalesce

from apps.core import permissions
from apps.surveys.models import Answer, Question, Survey, SurveyInvitation, SurveyReceipt
from apps.surveys.services import accepts_answers, is_due_passed


def _count(model) -> Coalesce:
    rows = (
        model.objects.filter(survey=OuterRef("pk"))
        .order_by()
        .values("survey")
        .annotate(n=Count("pk"))
        .values("n")
    )
    return Coalesce(Subquery(rows, output_field=IntegerField()), 0)


def survey_list(viewer, *, q: str = "", status: str = "") -> QuerySet:
    """RH et administrateur : tous, brouillons compris. Managers : tous les questionnaires
    publiés (ils voient les résultats). Salariés : ceux qui leur sont destinés."""
    rows = Survey.objects.annotate(
        invited_count=_count(SurveyInvitation),
        response_count=_count(SurveyReceipt),
        question_count=Count("questions"),
        is_invited=Exists(SurveyInvitation.objects.filter(survey=OuterRef("pk"), employee=viewer)),
        has_answered=Exists(SurveyReceipt.objects.filter(survey=OuterRef("pk"), employee=viewer)),
    )
    if not permissions.can(viewer, "surveys.manage"):
        rows = rows.exclude(status=Survey.Status.DRAFT)
        if not permissions.can(viewer, "surveys.view_results"):
            rows = rows.filter(is_invited=True)
    if q:
        rows = rows.filter(title__icontains=q)
    if status in Survey.Status.values:
        rows = rows.filter(status=status)
    return rows


def to_answer(viewer, today: date) -> list[Survey]:
    """Questionnaires ouverts, destinés à la personne, sans réponse de sa part."""
    return list(
        Survey.objects.filter(status=Survey.Status.OPEN, invitations__employee=viewer)
        .exclude(receipts__employee=viewer)
        .filter(Q(due_date__isnull=True) | Q(due_date__gte=today))
        .order_by("due_date", "pk")
    )


def can_answer(survey: Survey, viewer, today: date) -> bool:
    return (
        accepts_answers(survey, today)
        and SurveyInvitation.objects.filter(survey=survey, employee=viewer).exists()
        and not SurveyReceipt.objects.filter(survey=survey, employee=viewer).exists()
    )


def participation(survey: Survey) -> tuple[int, int]:
    """(réponses, personnes invitées) : des nombres seulement, jamais des noms."""
    return survey.receipts.count(), survey.invitations.count()


def results_visible(survey: Survey, today: date, responses: int) -> bool:
    """Résultats visibles seulement après la clôture ou l'échéance passée (L6-01), et à
    partir du seuil d'anonymat (3 réponses par défaut, M-10)."""
    finished = survey.status == Survey.Status.CLOSED or (
        survey.status == Survey.Status.OPEN and is_due_passed(survey, today)
    )
    return finished and responses >= survey.anonymity_threshold


@dataclass
class ScaleResult:
    question: Question
    average: float
    distribution: list[tuple[int, int, int]]  # (note, nombre, pourcentage), de 5 à 1
    comments: list[tuple[int, str]] = field(default_factory=list)  # (note, commentaire)


@dataclass
class TextResult:
    question: Question
    answers: list[str] = field(default_factory=list)


@dataclass
class Results:
    responses: int
    invited: int
    items: list = field(default_factory=list)

    @property
    def participation(self) -> int:
        return round(self.responses * 100 / self.invited) if self.invited else 0


def _scale_result(question: Question) -> ScaleResult:
    answers = Answer.objects.filter(question=question, score__isnull=False)
    counts = dict(answers.values_list("score").annotate(n=Count("pk")).order_by())
    total = sum(counts.values())
    average = sum(score * n for score, n in counts.items()) / total if total else 0
    # Commentaires : par note décroissante ; à note égale, dans l'ordre de la clé UUID
    # aléatoire, donc jamais dans l'ordre d'arrivée des réponses.
    comments = list(
        answers.exclude(comment="").order_by("-score", "id").values_list("score", "comment")
    )
    return ScaleResult(
        question,
        average,
        [
            (score, counts.get(score, 0), round(counts.get(score, 0) * 100 / total) if total else 0)
            for score in (5, 4, 3, 2, 1)
        ],
        comments,
    )


def _text_result(question: Question) -> TextResult:
    texts = Answer.objects.filter(question=question).exclude(text="").order_by("id")
    return TextResult(question, list(texts.values_list("text", flat=True)))


def survey_results(survey: Survey, today: date) -> Results | None:
    """Résultats agrégés, ou None s'ils ne peuvent pas être affichés (results_visible)."""
    responses, invited = participation(survey)
    if not results_visible(survey, today, responses):
        return None
    items = [
        _scale_result(question) if question.kind == Question.Kind.SCALE else _text_result(question)
        for question in survey.questions.all()
    ]
    return Results(responses, invited, items)
