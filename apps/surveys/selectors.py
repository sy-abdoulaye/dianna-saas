"""Lectures des questionnaires : liste, questionnaires à remplir, résultats.

`results_visible` est la seule règle d'affichage des résultats (L6-01, L6-05) : résultats,
commentaires, réponses libres et tout futur filtre ou export passent par `survey_results`,
qui renvoie None tant que la règle n'est pas remplie. Aucune lecture ne donne la liste des
répondants ni des non-répondants."""

from dataclasses import dataclass, field
from datetime import date

from django.db.models import (
    BooleanField,
    Count,
    Exists,
    ExpressionWrapper,
    IntegerField,
    OuterRef,
    Q,
    QuerySet,
    Subquery,
)
from django.db.models.functions import Coalesce

from apps.core import permissions
from apps.people.models import Employee
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


def survey_list(viewer: Employee, today: date, *, q: str = "", status: str = "") -> QuerySet:
    """RH et administrateur : tous, brouillons compris. Managers : tous les questionnaires
    publiés (ils voient les résultats). Salariés : ceux qui leur sont destinés.
    `can_answer_now` : ouvert, échéance non passée, destiné à la personne, sans réponse."""
    accepting = Q(status=Survey.Status.OPEN) & (Q(due_date__isnull=True) | Q(due_date__gte=today))
    rows = Survey.objects.annotate(
        invited_count=_count(SurveyInvitation),
        response_count=_count(SurveyReceipt),
        question_count=Count("questions"),
        is_invited=Exists(SurveyInvitation.objects.filter(survey=OuterRef("pk"), employee=viewer)),
        has_answered=Exists(SurveyReceipt.objects.filter(survey=OuterRef("pk"), employee=viewer)),
    )
    rows = rows.annotate(
        can_answer_now=ExpressionWrapper(
            accepting & Q(is_invited=True) & Q(has_answered=False), output_field=BooleanField()
        )
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


def to_answer(viewer: Employee, today: date) -> list[Survey]:
    """Questionnaires ouverts, destinés à la personne, sans réponse de sa part."""
    return list(
        Survey.objects.filter(status=Survey.Status.OPEN, invitations__employee=viewer)
        .exclude(receipts__employee=viewer)
        .filter(Q(due_date__isnull=True) | Q(due_date__gte=today))
        .order_by("due_date", "pk")
    )


def can_answer(survey: Survey, viewer: Employee, today: date) -> bool:
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


# Commentaires et réponses libres : les premiers sous chaque question, la suite par paquets
# (« Afficher plus ») pour rester lisible et léger à plusieurs centaines de réponses.
PREVIEW_SIZE = 5
MORE_SIZE = 20


@dataclass
class ScaleResult:
    question: Question
    average: float
    distribution: list[tuple[int, int, int]]  # (note, nombre, pourcentage), de 5 à 1
    comments: list[tuple[int, str]] = field(default_factory=list)  # aperçu (note, texte)
    comment_count: int = 0

    @property
    def hidden_count(self) -> int:
        """Commentaires au-delà de l'aperçu, chargés par « Afficher plus »."""
        return self.comment_count - len(self.comments)


@dataclass
class TextResult:
    question: Question
    answers: list[str] = field(default_factory=list)  # aperçu
    answer_count: int = 0

    @property
    def hidden_count(self) -> int:
        return self.answer_count - len(self.answers)


@dataclass
class Results:
    responses: int
    invited: int
    items: list = field(default_factory=list)

    @property
    def participation(self) -> int:
        return round(self.responses * 100 / self.invited) if self.invited else 0


def written_answers(question: Question) -> QuerySet:
    """Commentaires d'une question notée (note, texte) ou réponses libres (texte). Par note
    décroissante ; à note égale, dans l'ordre de la clé UUID aléatoire, donc jamais dans
    l'ordre d'arrivée des réponses."""
    answers = Answer.objects.filter(question=question)
    if question.kind == Question.Kind.SCALE:
        return answers.exclude(comment="").order_by("-score", "id").values_list("score", "comment")
    return answers.exclude(text="").order_by("id").values_list("text", flat=True)


def _scale_result(question: Question) -> ScaleResult:
    answers = Answer.objects.filter(question=question, score__isnull=False)
    counts = dict(answers.values_list("score").annotate(n=Count("pk")).order_by())
    total = sum(counts.values())
    average = sum(score * n for score, n in counts.items()) / total if total else 0
    comments = written_answers(question)
    return ScaleResult(
        question,
        average,
        [
            (score, counts.get(score, 0), round(counts.get(score, 0) * 100 / total) if total else 0)
            for score in (5, 4, 3, 2, 1)
        ],
        list(comments[:PREVIEW_SIZE]),
        comments.count(),
    )


def _text_result(question: Question) -> TextResult:
    texts = written_answers(question)
    return TextResult(question, list(texts[:PREVIEW_SIZE]), texts.count())


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


def more_written_answers(
    survey: Survey, order: int, start: int, today: date
) -> tuple[Question, list, int] | None:
    """Suite des commentaires (ou réponses libres) d'une question à partir de `start` :
    (question, paquet, nombre total). None si les résultats ne sont pas visibles : même
    règle que la page de résultats (results_visible)."""
    responses, _invited = participation(survey)
    question = survey.questions.filter(order=order).first()
    if question is None or not results_visible(survey, today, responses):
        return None
    rows = written_answers(question)
    return question, list(rows[start : start + MORE_SIZE]), rows.count()
