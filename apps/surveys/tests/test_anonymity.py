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


def test_response_keys_do_not_follow_the_order_of_receipts(company_a, open_survey):
    """Douze personnes répondent dans un ordre connu : le seul champ triable d'une réponse
    est sa clé UUID aléatoire, qui ne suit pas l'ordre d'arrivée ; reçu et réponse n'ont en
    commun que l'entreprise et le questionnaire."""
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


@pytest.mark.django_db(transaction=True)
def test_residual_link_in_the_database_by_transaction_number(company_a, open_survey):
    """Documente le risque résiduel L1-09 : le reçu est créé dans une sous-transaction de
    celle de la réponse, donc son numéro de transaction (xmin) vaut celui de la réponse + 1.
    Un accès SQL direct peut ainsi relier une personne à sa réponse ; l'application ne lit
    jamais cette colonne. CE TEST DEVRA CHANGER avec la réécriture groupée des réponses du
    lot 8 (le lien devra disparaître)."""
    from django.db import connection

    survey = open_survey()
    respondents = invited_people(survey)[:3]
    for person in respondents:
        answer(survey, person)
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT employee_id, xmin::text::bigint FROM surveys_surveyreceipt"
            " WHERE survey_id = %s",
            [survey.pk],
        )
        receipts = dict(cursor.fetchall())
        cursor.execute(
            "SELECT xmin::text::bigint FROM surveys_surveyresponse WHERE survey_id = %s",
            [survey.pk],
        )
        responses = {row[0] for row in cursor.fetchall()}
    assert {xmin - 1 for xmin in receipts.values()} == responses


def test_answering_writes_no_log_line(company_a, open_survey, caplog):
    """Aucune ligne de log, à aucun niveau, quand une personne répond (M-10, L6-03)."""
    import logging

    survey = open_survey()
    person = invited_people(survey)[0]
    with caplog.at_level(logging.DEBUG):
        answer(survey, person, comments=("Commentaire", ""), text="Réponse libre")
    assert caplog.records == []


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("read", ["results", "more"])
def test_reading_results_waits_for_an_answer_in_progress(company_a, open_survey, read):
    """Course à minuit (deux connexions réelles) : une réponse en cours tient le verrou
    exclusif du questionnaire ; une lecture des résultats (verrou partagé) attend qu'elle soit
    validée, et ne peut donc jamais précéder une réponse qui entrerait ensuite."""
    import threading
    import time

    from django.db import connection, transaction
    from django.utils import timezone

    from apps.core.models import Company
    from apps.core.tenancy import tenant_context
    from apps.surveys import selectors, services
    from apps.surveys.models import Question, Survey

    survey = open_survey()
    person = invited_people(survey)[0]
    company = Company.objects.get(pk=company_a.company.pk)
    locked, events = threading.Event(), []

    def answer_slowly():
        try:
            with tenant_context(company), transaction.atomic():
                current = Survey.objects.select_for_update().get(pk=survey.pk)
                locked.set()
                time.sleep(0.5)
                scores = {
                    q.pk: {"score": 4}
                    for q in Question.objects.filter(survey=current, kind=Question.Kind.SCALE)
                }
                services.submit_answers(current, person, scores)
            events.append(("answer committed", time.monotonic()))
        finally:
            connection.close()

    def read_results():
        try:
            locked.wait(5)
            with tenant_context(company):
                current = Survey.objects.get(pk=survey.pk)
                if read == "results":
                    selectors.survey_results(current, timezone.localdate())
                else:
                    selectors.more_written_answers(current, 1, 0, timezone.localdate())
            events.append(("results read", time.monotonic()))
        finally:
            connection.close()

    threads = [threading.Thread(target=answer_slowly), threading.Thread(target=read_results)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10)
    assert [name for name, _at in sorted(events, key=lambda e: e[1])] == [
        "answer committed",
        "results read",
    ]
