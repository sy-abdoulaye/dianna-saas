"""Anonymat réel des questionnaires (M-10, L6-01 à L6-03) : aucune requête ni aucun champ ne
permet de relier une réponse à son auteur."""

import pytest
from django.db import models
from django_tasks_db.models import DBTaskResult

from apps.core.models import AuditLog, Notification, Timestamped
from apps.people.models import Employee
from apps.surveys.models import Answer, SurveyReceipt, SurveyResponse
from apps.surveys.tests.conftest import answer, invited_people

pytestmark = pytest.mark.django_db

ANONYMOUS_MODELS = (SurveyResponse, Answer)


@pytest.mark.parametrize("model", ANONYMOUS_MODELS, ids=lambda m: m.__name__)
def test_anonymous_rows_have_no_link_to_a_person_no_date_and_a_random_key(model):
    fields = model._meta.get_fields(include_hidden=True)
    related = {f.related_model for f in fields if f.is_relation and f.related_model}
    assert Employee not in related and SurveyReceipt not in related
    assert not any(isinstance(f, (models.DateField, models.DateTimeField)) for f in fields)
    assert not issubclass(model, Timestamped)
    pk = model._meta.pk
    assert isinstance(pk, models.UUIDField) and pk.default.__name__ == "uuid4"
    assert "submitted_on" not in {f.name for f in fields}


def test_receipt_and_response_share_no_key_and_no_order(company_a, open_survey):
    """Douze personnes répondent dans un ordre connu : aucun champ des réponses ne permet de
    retrouver cet ordre (la clé UUID aléatoire ne suit pas l'ordre d'arrivée)."""
    survey = open_survey(extra_people=12)
    respondents = invited_people(survey)[:12]
    for person in respondents:
        answer(survey, person)
    receipts_order = list(
        SurveyReceipt.all_companies.filter(survey=survey)
        .order_by("created_at", "pk")
        .values_list("employee_id", flat=True)
    )
    assert receipts_order == [p.pk for p in respondents]
    responses = SurveyResponse.all_companies.filter(survey=survey)
    orderable = [
        f.name for f in SurveyResponse._meta.concrete_fields if f.name not in ("company", "survey")
    ]
    assert orderable == ["id"]
    by_key = list(responses.order_by("id").values_list("id", flat=True))
    inserted = list(responses.values_list("id", flat=True))  # ordre physique (L1-09)
    assert len(by_key) == 12
    # Une coïncidence sur 12! : l'ordre des clés ne reproduit pas l'ordre d'insertion.
    assert by_key != inserted
    receipt_columns = {f.column for f in SurveyReceipt._meta.concrete_fields}
    response_columns = {f.column for f in SurveyResponse._meta.concrete_fields}
    # Colonnes communes : l'entreprise, le questionnaire et le nom « id », qui n'a rien en
    # commun (entier du reçu, UUID aléatoire de la réponse).
    assert receipt_columns & response_columns == {"id", "company_id", "survey_id"}
    assert not isinstance(SurveyReceipt._meta.pk, models.UUIDField)


def test_answering_writes_no_journal_line_no_notification_and_no_task(company_a, open_survey):
    survey = open_survey()
    person = invited_people(survey)[0]
    counts = (
        AuditLog.all_companies.count(),
        Notification.all_companies.count(),
        DBTaskResult.objects.count(),
    )
    answer(survey, person, comments=("Très bonne équipe", ""), text="Plus de réunions courtes")
    assert (
        AuditLog.all_companies.count(),
        Notification.all_companies.count(),
        DBTaskResult.objects.count(),
    ) == counts
    assert Answer.all_companies.filter(response__survey=survey).count() == 3
