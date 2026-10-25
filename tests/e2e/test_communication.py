"""Parcours du lot 6 : annonce publiée puis lue (texte affiché sans HTML), suppression
annulée ; questionnaire créé, modifié, publié, rempli, puis résultats après la clôture."""

import pytest
from playwright.sync_api import expect

from apps.core.context import ActionContext
from apps.core.tenancy import tenant_context
from apps.surveys import services
from apps.surveys.models import Survey
from tests.e2e.test_requests import sign_in
from tests.factories import EmployeeFactory

pytestmark = pytest.mark.django_db(transaction=True)

SCREENSHOTS = None  # dossier où enregistrer des captures (vérification manuelle)


def shot(page, name):
    if SCREENSHOTS:
        page.screenshot(path=f"{SCREENSHOTS}/{name}.png", full_page=True)


def test_hr_publishes_an_announcement_that_an_employee_reads(
    browser, urls, company_a, console_errors
):
    hr = browser.new_context(locale="fr-FR")
    page = hr.new_page()
    page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
    sign_in(page, urls, company_a.hr)
    page.goto(urls("/annonces/"))
    page.get_by_role("button", name="Nouvelle annonce").click()
    dialog = page.locator("dialog[open]")
    dialog.get_by_label("Titre").fill("Déménagement du service paie")
    dialog.get_by_label("Message").fill("Trop court")
    dialog.get_by_role("button", name="Publier l'annonce").click()
    expect(dialog).to_contain_text("Le message est trop court (15 caractères minimum).")
    dialog.get_by_label("Message").fill(
        "<script>alert('x')</script> Plan d'accès : https://exemple.fr/plan"
    )
    dialog.get_by_label("Épingler en haut de la liste").check()
    dialog.get_by_role("button", name="Publier l'annonce").click()
    expect(page.locator("#toasts .toast").last).to_contain_text("Annonce publiée")
    expect(page.get_by_role("heading", level=1)).to_have_text("Déménagement du service paie")
    expect(page.get_by_text("Lectures")).to_be_visible()
    shot(page, "annonce-rh")
    hr.close()

    employee = browser.new_context(locale="fr-FR")
    page = employee.new_page()
    sign_in(page, urls, company_a.employee)
    page.goto(urls("/annonces/"))
    expect(page.locator(".page-head .sub")).to_contain_text("2 annonces non lues")
    shot(page, "annonces-salarie")
    page.get_by_role("link", name="Déménagement du service paie").click()
    article = page.locator("article")
    expect(article).to_contain_text("<script>alert('x')</script>")
    expect(article.get_by_role("link", name="https://exemple.fr/plan")).to_be_visible()
    expect(page.get_by_role("button", name="Modifier")).to_have_count(0)
    page.goto(urls("/annonces/"))
    expect(page.locator(".page-head .sub")).to_contain_text("1 annonce non lue")
    employee.close()


def test_hr_deletes_an_announcement_then_undoes_it(page, urls, company_a, console_errors):
    announcement = company_a.requests["announcement"]
    sign_in(page, urls, company_a.hr)
    page.goto(urls(f"/annonces/{announcement.public_id}/"))
    page.get_by_role("button", name="Supprimer").click()
    page.locator("dialog[open]").get_by_role("button", name="Supprimer").click()
    toast = page.locator("#toasts .toast").last
    expect(toast).to_contain_text("Annonce supprimée")
    expect(page.get_by_role("heading", level=1)).to_have_text("Communication interne")
    expect(page.locator("#results")).not_to_contain_text(announcement.title)
    toast.get_by_role("button", name="Annuler").click()
    expect(page.locator("#toasts .toast").last).to_contain_text("Suppression annulée")
    expect(page.locator("#results")).to_contain_text(announcement.title)
    assert console_errors == []


def hr_creates_edits_and_publishes(page, urls, company_a):
    sign_in(page, urls, company_a.hr)
    page.goto(urls("/questionnaires/"))
    page.get_by_role("button", name="Créer un questionnaire").click()
    dialog = page.locator("dialog[open]")
    dialog.get_by_label("Titre").fill("Ambiance 2026")
    dialog.get_by_label("Questions notées de 1 à 5 (une par ligne)").fill(
        "Je me sens bien dans mon équipe."
    )
    dialog.get_by_role("button", name="Créer le brouillon").click()
    expect(page.locator("#toasts .toast").last).to_contain_text("Brouillon créé")
    page.get_by_role("button", name="Modifier le brouillon").click()
    dialog = page.locator("dialog[open]")
    dialog.get_by_label("Question ouverte (facultative)").fill("Une idée ?")
    dialog.get_by_role("button", name="Enregistrer").click()
    expect(page.locator("#toasts .toast").last).to_contain_text("Brouillon modifié")
    expect(page.locator("main")).to_contain_text("Une idée ?")
    page.get_by_role("button", name="Publier").click()
    page.locator("dialog[open]").get_by_role("button", name="Publier").click()
    expect(page.locator("#toasts .toast").last).to_contain_text("Questionnaire publié")


def employee_answers_with_a_comment(browser, urls, company_a):
    employee = browser.new_context(locale="fr-FR")
    page = employee.new_page()
    sign_in(page, urls, company_a.employee)
    page.goto(urls("/questionnaires/"))
    expect(page.locator(".banner")).to_contain_text("1 questionnaire à remplir.")
    page.get_by_role("link", name="Ambiance 2026").first.click()
    page.get_by_role("button", name="Envoyer mes réponses").click()
    expect(page.locator("main")).to_contain_text("Choisissez une note de 1 à 5.")
    page.locator("label", has_text="4").first.click()
    page.get_by_label("Commentaire (facultatif)").fill("Une équipe soudée.")
    shot(page, "questionnaire-reponse")
    page.get_by_role("button", name="Envoyer mes réponses").click()
    expect(page.locator("#toasts .toast").last).to_contain_text("Réponses envoyées")
    expect(page.locator("main")).to_contain_text("Merci, votre réponse est enregistrée")
    employee.close()


def four_colleagues_answer(company_a):
    with tenant_context(company_a.company):
        survey = Survey.objects.get(title="Ambiance 2026")
        question = survey.questions.get(order=1)
        others = list(survey.invitations.exclude(employee=company_a.employee))[:4]
        for invitation in others:
            services.submit_answers(survey, invitation.employee, {question.pk: {"score": 2}})


def test_survey_from_draft_to_results_after_closing(browser, urls, company_a, console_errors):
    for index in range(4):
        EmployeeFactory(company=company_a.company, last_name=f"Collegue{index}", user=None)
    hr = browser.new_context(locale="fr-FR")
    page = hr.new_page()
    hr_creates_edits_and_publishes(page, urls, company_a)
    employee_answers_with_a_comment(browser, urls, company_a)
    four_colleagues_answer(company_a)  # 5 réponses : seuil d'anonymat
    page.reload()
    # La RH fait partie du public et n'a pas répondu : « Répondre » ou « Résultats ».
    page.get_by_role("link", name="Résultats").click()
    expect(page.locator("main")).to_contain_text("5 réponses reçues")
    expect(page.locator("main")).to_contain_text("Les résultats seront visibles à la clôture")
    page.get_by_role("button", name="Clore le questionnaire").click()
    page.locator("dialog[open]").get_by_role("button", name="Clore").click()
    expect(page.locator("#toasts .toast").last).to_contain_text("Questionnaire clos")
    expect(page.locator("main")).to_contain_text("2,4 / 5")  # (4 + 4 × 2) / 5
    expect(page.locator("main")).to_contain_text("Une équipe soudée.")
    shot(page, "questionnaire-resultats")
    hr.close()
    assert console_errors == []


def test_show_more_moves_the_keyboard_focus_to_the_first_loaded_comment(
    page, urls, company_a, console_errors
):
    """WCAG 2.4.3 : après « Afficher plus » (clavier), le focus va sur le premier commentaire
    chargé au lieu d'être perdu avec le bouton remplacé."""
    people = [
        EmployeeFactory(company=company_a.company, last_name=f"Avis{index}", user=None)
        for index in range(12)
    ]
    with tenant_context(company_a.company):
        survey = services.create_draft(
            services.DraftData("Ambiance", "all", None, ["Je me sens bien."]),
            context=ActionContext(company_a.hr),
        )
        services.publish(survey, context=ActionContext(company_a.hr))
        question = survey.questions.get(order=1)
        for index, person in enumerate(people):
            services.submit_answers(
                survey,
                person,
                {question.pk: {"score": 4, "comment": f"Commentaire numéro {index:02d}"}},
            )
        services.close(Survey.objects.get(pk=survey.pk), context=ActionContext(company_a.hr))
    sign_in(page, urls, company_a.hr)
    page.goto(urls(f"/questionnaires/{survey.public_id}/"))
    more = page.get_by_role("button", name="Afficher plus (7 restants)")
    more.focus()
    page.keyboard.press("Enter")
    expect(page.locator("main")).to_contain_text("Commentaires (12)")
    expect(more).to_have_count(0)
    focused = page.locator(":focus")
    expect(focused).to_have_attribute("tabindex", "-1")
    expect(focused).to_contain_text("Commentaire numéro")
    assert page.locator(".comments li").count() == 12
    assert console_errors == []
