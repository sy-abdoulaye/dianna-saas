"""Questionnaires (docs/modules/09-questionnaires.md) : cycle de vie, public figé, réponse
unique, seuil d'anonymat partout, résultats après la clôture seulement (L6-01)."""

import json
from datetime import timedelta

import pytest
from django.core.management import call_command

from apps.core.models import AuditLog, Notification
from apps.core.tenancy import tenant_context
from apps.surveys import services
from apps.surveys.models import Answer, Question, Survey, SurveyInvitation, SurveyReceipt
from apps.surveys.tests.conftest import answer, close, invited_people, today
from tests.factories import EmployeeFactory

pytestmark = pytest.mark.django_db

DRAFT = {
    "title": "Besoins de formation",
    "audience": "all",
    "due_date": "",
    "questions": "Je dispose des outils nécessaires.\n\n  Mon équipe m'aide.  ",
    "open_question": "Quelle formation vous aiderait ?",
}


def url(survey, suffix=""):
    return f"/questionnaires/{survey.public_id}/{suffix}"


def toast(response) -> dict:
    return json.loads(response["HX-Trigger"])["toast"]


def results_page(client, survey) -> str:
    return client.get(url(survey) + "?vue=resultats").content.decode()


# ---------- Brouillon ----------


def test_hr_creates_then_edits_a_draft_only_while_it_is_a_draft(client_for, company_a):
    client = client_for(company_a.hr)
    created = client.post("/questionnaires/nouveau/", DRAFT)
    assert toast(created)["title"] == "Brouillon créé"
    survey = Survey.all_companies.get(title="Besoins de formation")
    assert survey.status == "draft"
    labels = list(Question.all_companies.filter(survey=survey).values_list("kind", "label"))
    assert labels == [
        ("scale", "Je dispose des outils nécessaires."),
        ("scale", "Mon équipe m'aide."),
        ("text", "Quelle formation vous aiderait ?"),
    ]
    edit = client.get(url(survey, "modifier/")).content.decode()
    assert "Modifier le brouillon" in edit and "Mon équipe m&#x27;aide." in edit
    client.post(
        url(survey, "modifier/"), {**DRAFT, "title": "Formation 2027", "audience": "managers"}
    )
    survey.refresh_from_db()
    assert survey.title == "Formation 2027" and survey.audience == "managers"
    assert Question.all_companies.filter(survey=survey).count() == 3
    client.post(url(survey, "modifier/"), {**DRAFT, "audience": "all"})
    client.post(url(survey, "publier/"))
    assert client.get(url(survey, "modifier/")).status_code == 404  # publié : plus modifiable


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"title": ""}, "Donnez un titre au questionnaire."),
        ({"questions": "  \n "}, "Ajoutez au moins une question."),
        ({"due_date": "2020-01-01"}, "L&#x27;échéance ne peut pas être passée."),
    ],
)
def test_draft_controls(client_for, company_a, changes, message):
    response = client_for(company_a.hr).post("/questionnaires/nouveau/", {**DRAFT, **changes})
    assert response.status_code == 422
    assert message in response.content.decode()


def test_draft_is_hidden_from_employees_and_managers_and_can_be_deleted(client_for, company_a):
    draft = company_a.requests["draft_survey"]
    for who in ("employee", "manager"):
        client = client_for(getattr(company_a, who))
        assert client.get(url(draft)).status_code == 403
        assert "Formation 2027" not in client.get("/questionnaires/").content.decode()
    hr = client_for(company_a.hr)
    assert "Aperçu du brouillon" in hr.get(url(draft)).content.decode()
    assert "Brouillons" in hr.get("/questionnaires/").content.decode()
    deleted = hr.post(url(draft, "supprimer/"))
    assert toast(deleted)["title"] == "Brouillon supprimé"
    assert not Survey.all_companies.filter(pk=draft.pk).exists()


# ---------- Publication ----------


def test_publication_freezes_the_audience_and_notifies_it(client_for, company_a):
    draft = company_a.requests["draft_survey"]
    response = client_for(company_a.hr).post(url(draft, "publier/"))
    assert toast(response)["title"] == "Questionnaire publié"
    invited = set(
        SurveyInvitation.all_companies.filter(survey=draft).values_list("employee_id", flat=True)
    )
    present = {
        company_a.admin.pk,
        company_a.hr.pk,
        company_a.manager.pk,
        company_a.employee.pk,
        company_a.pending.pk,
    }
    assert invited == present
    notified = set(
        Notification.all_companies.filter(url=url(draft)).values_list("recipient_id", flat=True)
    )
    assert notified == present - {company_a.hr.pk}  # l'auteur n'est pas notifié
    # Arrivé après la publication : hors du public figé, il ne peut pas répondre.
    late = EmployeeFactory(company=company_a.company)
    with tenant_context(company_a.company):
        survey = Survey.objects.get(pk=draft.pk)
        with pytest.raises(services.SurveyError, match="ne vous est pas destiné"):
            services.submit_answers(survey, late, {})


def test_audience_smaller_than_the_threshold_cannot_be_published(client_for, company_a):
    with tenant_context(company_a.company):
        survey = services.create_draft(
            services.DraftData("Intégration", "new_hires", None, ["Mon accueil s'est bien passé."]),
            actor=company_a.hr,
        )
    EmployeeFactory(company=company_a.company, arrival_date=today() - timedelta(days=30))
    response = client_for(company_a.hr).post(url(survey, "publier/"))
    assert response.status_code == 409
    assert "Le public compte moins de 3 personnes" in toast(response)["title"]
    survey.refresh_from_db()
    assert survey.status == "draft"
    assert not SurveyInvitation.all_companies.filter(survey=survey).exists()


def test_managers_audience_is_people_with_direct_reports(company_a):
    with tenant_context(company_a.company):
        people = set(services.audience_people("managers", today()))
    assert people == {company_a.manager}


# ---------- Réponse ----------


def test_employee_answers_once_with_a_comment_even_when_resending(
    client_for, company_a, open_survey
):
    survey = open_survey()
    client = client_for(company_a.employee)
    page = client.get("/questionnaires/").content.decode()
    assert "questionnaire à remplir" in page or "questionnaires à remplir" in page
    form = client.get(url(survey)).content.decode()
    assert "Vos réponses sont anonymes" in form and "Commentaire (facultatif)" in form
    questions = list(Question.all_companies.filter(survey=survey).order_by("order"))
    missing = client.post(url(survey, "repondre/"), {"q1": "4"})
    assert (
        missing.status_code == 422 and "Choisissez une note de 1 à 5." in missing.content.decode()
    )
    data = {"q1": "5", "c1": "Très bonne entente.", "q2": "3", "q3": "Moins de réunions"}
    sent = client.post(url(survey, "repondre/"), data)
    assert toast(sent)["title"] == "Réponses envoyées"
    again = client.post(url(survey, "repondre/"), data)
    assert again.status_code == 409
    assert toast(again)["title"] == "Vous avez déjà répondu à ce questionnaire."
    assert (
        SurveyReceipt.all_companies.filter(survey=survey, employee=company_a.employee).count() == 1
    )
    comment = Answer.all_companies.get(question=questions[0])
    assert (comment.score, comment.comment) == (5, "Très bonne entente.")
    done = client.get(url(survey)).content.decode()
    assert "Merci, votre réponse est enregistrée" in done


def test_resending_the_same_form_is_refused_by_the_service(company_a, open_survey):
    survey = open_survey()
    answer(survey, company_a.employee)
    with pytest.raises(services.SurveyError, match="déjà répondu"):
        answer(survey, company_a.employee)


def test_answers_are_refused_after_the_due_date(company_a, open_survey):
    survey = open_survey(due_date=today() + timedelta(days=1))
    Survey.all_companies.filter(pk=survey.pk).update(due_date=today() - timedelta(days=1))
    survey.refresh_from_db()
    with pytest.raises(services.SurveyError, match="n'accepte plus"):
        answer(survey, company_a.employee)


def test_employee_does_not_see_a_survey_that_is_not_for_them(client_for, company_a):
    with tenant_context(company_a.company):
        for index in range(3):
            report = EmployeeFactory(company=company_a.company, last_name=f"Equipe{index}")
            report.manager = EmployeeFactory(company=company_a.company, last_name=f"Chef{index}")
            report.save()
        survey = services.create_draft(
            services.DraftData("Managers", "managers", None, ["Question"]), actor=company_a.hr
        )
        services.publish(survey, actor=company_a.hr)
    client = client_for(company_a.employee)
    assert (
        "Managers" not in client.get("/questionnaires/").content.decode().split('id="results"')[1]
    )
    assert client.get(url(survey)).status_code == 404


# ---------- Résultats ----------


def test_open_survey_shows_only_the_number_of_answers_never_who(client_for, company_a, open_survey):
    survey = open_survey()
    for person in invited_people(survey)[:4]:
        answer(survey, person, comments=("Commentaire secret", ""))
    for who in ("manager", "hr", "admin"):
        page = results_page(client_for(getattr(company_a, who)), survey)
        assert "4 réponses reçues" in page
        assert "Les résultats seront visibles à la clôture" in page
        assert "Commentaire secret" not in page
        main = page.split("<main", 1)[1]
        for person in invited_people(survey):
            assert person.last_name not in main  # ni répondants ni non-répondants


def test_employee_cannot_see_results(client_for, company_a, open_survey):
    survey = open_survey()
    assert client_for(company_a.employee).get(url(survey) + "?vue=resultats").status_code == 403


def test_two_answers_keep_results_and_comments_hidden_after_closing(
    client_for, company_a, open_survey
):
    survey = open_survey()
    for person in invited_people(survey)[:2]:
        answer(survey, person, comments=("Commentaire visible ?", ""))
    close(survey, company_a.hr)
    page = results_page(client_for(company_a.manager), survey)
    assert "Résultats masqués" in page
    assert "Moins de 3 personnes ont répondu (2)" in page
    assert "Commentaire visible ?" not in page
    with tenant_context(company_a.company):
        from apps.surveys import selectors

        assert selectors.survey_results(Survey.objects.get(pk=survey.pk), today()) is None


def test_closed_survey_shows_results_with_comments_sorted_by_score(
    client_for, company_a, open_survey
):
    survey = open_survey()
    people = invited_people(survey)
    answer(survey, people[0], scores=(2, 3), comments=("Charge trop lourde", ""))
    answer(survey, people[1], scores=(5, 4), comments=("Très bonne équipe", ""), text="Café")
    answer(survey, people[2], scores=(4, 4))
    client = client_for(company_a.hr)
    close_response = client.post(url(survey, "clore/"))
    assert toast(close_response)["title"] == "Questionnaire clos"
    page = results_page(client, survey)
    assert "3,7 / 5" in page  # (2 + 5 + 4) / 3
    assert page.index("Très bonne équipe") < page.index("Charge trop lourde")
    assert "Note 5" in page and "Note 2" in page and "Commentaires (2)" in page
    assert "Café" in page
    assert "Participation" in page and "Réponses" in page
    log = AuditLog.all_companies.filter(action="surveys.closed").get()
    assert "Charge" not in log.summary


def test_due_date_passed_shows_results_and_the_daily_task_closes_it(
    client_for, company_a, open_survey, run_tasks
):
    survey = open_survey(due_date=today() + timedelta(days=1))
    for person in invited_people(survey)[:3]:
        answer(survey, person)
    Survey.all_companies.filter(pk=survey.pk).update(due_date=today() - timedelta(days=1))
    assert "/ 5" in results_page(client_for(company_a.manager), survey)
    call_command("enqueue_daily_tasks", verbosity=0)
    run_tasks()
    survey.refresh_from_db()
    assert survey.status == "closed"
    assert AuditLog.all_companies.filter(
        action="surveys.closed", summary__contains="automatiquement"
    ).exists()


def test_manager_who_has_not_answered_switches_between_answer_and_results(
    client_for, company_a, open_survey
):
    survey = open_survey()
    client = client_for(company_a.manager)
    page = client.get(url(survey)).content.decode()
    assert "Envoyer mes réponses" in page
    assert 'href="/questionnaires/' in page and "?vue=resultats" in page
    assert "Les résultats seront visibles à la clôture" in results_page(client, survey)
