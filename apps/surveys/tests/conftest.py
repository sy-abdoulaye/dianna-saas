import pytest
from django.utils import timezone

from apps.core.tenancy import tenant_context
from apps.surveys import services
from apps.surveys.models import Question, Survey
from tests.factories import EmployeeFactory


@pytest.fixture
def open_survey(company_a):
    """Questionnaire publié pour toute l'entreprise (fiches de la fixture et 8 salariés de
    plus) : deux questions notées et une question ouverte."""

    def _make(*, audience="all", extra_people=8, due_date=None):
        for index in range(extra_people):
            EmployeeFactory(company=company_a.company, last_name=f"Repondant{index}", user=None)
        with tenant_context(company_a.company):
            survey = services.create_draft(
                services.DraftData(
                    title="Qualité de vie au travail",
                    audience=audience,
                    due_date=due_date,
                    scale_questions=[
                        "Je me sens bien dans mon équipe.",
                        "Ma charge est soutenable.",
                    ],
                    open_question="Qu'est-ce qui pourrait améliorer votre quotidien ?",
                ),
                actor=company_a.hr,
            )
            services.publish(survey, actor=company_a.hr)
            survey.refresh_from_db()
        return survey

    return _make


def answer(survey, employee, *, scores=(4, 3), comments=("", ""), text=""):
    """Réponse par le service, comme le formulaire."""
    with tenant_context(survey.company):
        questions = list(survey.questions.all())
        raw = {}
        for question, score, comment in zip(
            [q for q in questions if q.kind == Question.Kind.SCALE], scores, comments, strict=False
        ):
            raw[question.pk] = {"score": score, "comment": comment}
        for question in questions:
            if question.kind == Question.Kind.TEXT:
                raw[question.pk] = {"text": text}
        services.submit_answers(survey, employee, raw)


def close(survey, actor):
    with tenant_context(survey.company):
        services.close(Survey.objects.get(pk=survey.pk), actor=actor)


def invited_people(survey):
    with tenant_context(survey.company):
        return [
            inv.employee for inv in survey.invitations.select_related("employee").order_by("pk")
        ]


def today():
    return timezone.localdate()
