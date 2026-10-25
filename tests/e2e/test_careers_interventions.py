"""Parcours du lot 7 (docs/08-prompts-claude-code.md, parcours 3 et 7) : entretien individuel
complet jusqu'à la clôture et la note de suivi ; compte rendu d'intervention envoyé, complété
puis validé ; blocs répétables sans perte de saisie ; allers-retours des onglets et filtres."""

import re

import pytest
from django.utils import timezone
from playwright.sync_api import expect

from tests.e2e.test_requests import sign_in
from tests.e2e.test_round_trips import round_trip

pytestmark = pytest.mark.django_db(transaction=True)


def toast(page):
    return page.locator("#toasts .toast").last


def rate(page, competency: str, score: str):
    page.locator("fieldset", has_text=competency).locator("label", has_text=score).click()


def test_individual_review_from_evaluation_to_closure_and_follow_up_note(
    browser, urls, company_a, console_errors
):
    review = company_a.requests["review"]  # auto-évaluation faite, au manager d'agir
    manager_context = browser.new_context(locale="fr-FR")
    page = manager_context.new_page()
    sign_in(page, urls, company_a.manager)
    page.goto(urls("/carriere/"))
    page.get_by_role("link", name="Compléter").first.click()
    expect(page).to_have_url(re.compile(str(review.public_id)))
    page.get_by_label("Votre bilan").fill("Une très belle année, beaucoup de progrès.")
    # L'évaluation est bloquée tant que les quatre compétences ne sont pas notées.
    page.get_by_role("button", name="Enregistrer l'évaluation").click()
    expect(page.get_by_text("Notez toutes les compétences de 1 à 4.").first).to_be_visible()
    for competency in ("Relation client", "Autonomie", "Travail en équipe", "Maîtrise des outils"):
        rate(page, competency, "3")
    page.get_by_label("Points forts").fill("Rigueur et écoute.")
    page.get_by_label("Axes de progrès").fill("Déléguer davantage.")
    page.locator('[name="objectives-0-title"]').fill("Former un nouvel arrivant")
    page.get_by_role("button", name="Enregistrer l'évaluation").click()
    expect(toast(page)).to_contain_text("Évaluation enregistrée")
    page.get_by_label("Date de l'entretien").fill(timezone.localdate().isoformat())
    page.get_by_role("button", name="Planifier").click()
    expect(toast(page)).to_contain_text("Entretien planifié")
    page.get_by_role("button", name="Marquer l'entretien comme réalisé").click()
    page.locator("dialog[open]").get_by_role("button", name="Oui, il a eu lieu").click()
    expect(page.get_by_role("button", name="Signer l'entretien")).to_be_visible()

    employee_context = browser.new_context(locale="fr-FR")
    employee = employee_context.new_page()
    sign_in(employee, urls, company_a.employee)
    employee.goto(urls(f"/carriere/{review.public_id}/"))
    employee.get_by_role("button", name="Signer l'entretien").click()
    dialog = employee.locator("dialog[open]")
    dialog.get_by_label("Votre commentaire (facultatif)").fill("Merci pour cet échange.")
    dialog.get_by_role("button", name="Signer l'entretien").click()
    expect(toast(employee)).to_contain_text("Signature enregistrée")

    page.reload()
    page.get_by_role("button", name="Signer l'entretien").click()
    page.locator("dialog[open]").get_by_role("button", name="Signer l'entretien").click()
    expect(toast(page)).to_contain_text("Entretien clos")
    expect(page.get_by_text("Entretien clos.")).to_be_visible()
    page.get_by_role("link", name="Voir la fiche de suivi").click()
    expect(page.get_by_text("clos et signé.")).to_be_visible()
    assert console_errors == []
    manager_context.close()
    employee_context.close()


def test_launching_a_review_then_undo_removes_it(page, urls, company_a):
    sign_in(page, urls, company_a.manager)
    page.goto(urls("/carriere/"))
    page.get_by_role("button", name="Lancer un entretien").click()
    dialog = page.locator("dialog[open]")
    dialog.get_by_label("Collaborateur").select_option(label=company_a.employee.full_name)
    dialog.get_by_label("Type d'entretien").select_option("professional")
    dialog.get_by_label("Motif").select_option("periodic")
    dialog.get_by_role("button", name="Lancer l'entretien").click()
    expect(toast(page)).to_contain_text("Entretien lancé")
    rows = page.locator("#results tbody tr", has_text="Entretien de parcours professionnel")
    expect(rows).to_have_count(2)  # celui de la fixture (clos) et le nouveau
    toast(page).get_by_role("button", name="Annuler").click()
    expect(toast(page)).to_contain_text("Lancement annulé")
    expect(rows).to_have_count(1)


def fill_block(page, prefix: str, index: int, text: str, percent: str):
    page.locator(f'[name="{prefix}-{index}-description"]').fill(text)
    page.locator(f'[name="{prefix}-{index}-completion"]').fill(percent)


def test_report_with_two_works_changes_requested_then_validated(browser, urls, company_a):
    employee_context = browser.new_context(locale="fr-FR")
    page = employee_context.new_page()
    sign_in(page, urls, company_a.employee)
    page.goto(urls("/interventions/nouveau/"))
    page.locator('[name="mission"]').fill("Refonte de l'espace client")
    fill_block(page, "done", 0, "Module de paiement", "60")
    page.get_by_role("button", name="Ajouter un travail réalisé").click()
    expect(page.locator('[name="done-1-description"]')).to_be_focused()
    fill_block(page, "done", 1, "Plan de tests", "150")
    fill_block(page, "next", 0, "Tests de bout en bout", "0")
    page.get_by_label("Visibilité de l'intervention").select_option("uncertain")
    page.get_by_label("Date de fin prévue").fill("2031-11-30")
    page.get_by_role("button", name="Envoyer à mon manager").click()
    expect(page.get_by_text("Entre 0 et 100.").first).to_be_visible()
    expect(page.locator('[name="done-0-description"]')).to_have_value("Module de paiement")
    page.locator('[name="done-1-completion"]').fill("100")
    page.get_by_role("button", name="Envoyer à mon manager").click()
    expect(toast(page)).to_contain_text("Compte rendu envoyé")
    expect(page.get_by_role("heading", level=1)).to_contain_text("Compte rendu")
    detail_url = page.url

    manager_context = browser.new_context(locale="fr-FR")
    manager = manager_context.new_page()
    sign_in(manager, urls, company_a.manager)
    manager.goto(urls("/interventions/?onglet=a-valider"))
    manager.locator("#results tr", has_text="Refonte de l'espace client").get_by_role(
        "link", name="Valider"
    ).click()
    manager.get_by_role("button", name="Demander un complément").click()
    dialog = manager.locator("dialog[open]")
    dialog.get_by_label("Ce qu'il faut compléter").fill("Précise le risque de retard.")
    dialog.get_by_role("button", name="Envoyer la demande").click()
    expect(toast(manager)).to_contain_text("Complément demandé")

    page.goto(detail_url)
    page.get_by_role("link", name="Modifier").click()
    expect(page.get_by_text("Précise le risque de retard.")).to_be_visible()
    page.get_by_label("Points de suivi, risques et besoins").fill("Accès à l'API bancaire.")
    page.get_by_role("button", name="Envoyer à mon manager").click()
    expect(toast(page)).to_contain_text("Compte rendu envoyé")

    manager.goto(detail_url)
    manager.get_by_role("button", name="Valider").click()
    manager.locator("dialog[open]").get_by_role("button", name="Valider").click()
    expect(toast(manager)).to_contain_text("Compte rendu validé")
    manager.goto(urls("/interventions/?onglet=a-valider"))
    expect(manager.locator("#results")).not_to_contain_text("Refonte de l'espace client")
    employee_context.close()
    manager_context.close()


def test_adding_a_third_block_keeps_the_first_two_and_removal_can_be_undone(page, urls, company_a):
    sign_in(page, urls, company_a.employee)
    page.goto(urls("/interventions/nouveau/"))
    fill_block(page, "done", 0, "Premier travail", "10")
    page.get_by_role("button", name="Ajouter un travail réalisé").click()
    fill_block(page, "done", 1, "Deuxième travail", "20")
    page.get_by_role("button", name="Ajouter un travail réalisé").click()
    expect(page.locator('[name="done-2-description"]')).to_be_visible()
    expect(page.locator('[name="done-0-description"]')).to_have_value("Premier travail")
    expect(page.locator('[name="done-1-description"]')).to_have_value("Deuxième travail")
    rows = page.locator("#done-rows [data-repeat-row]:visible")
    expect(rows).to_have_count(3)
    rows.nth(0).get_by_role("button", name="Retirer").click()
    expect(rows).to_have_count(2)
    expect(rows.nth(0).locator("[data-repeat-number]")).to_have_text("Travail réalisé 1")
    toast(page).get_by_role("button", name="Annuler").click()
    expect(rows).to_have_count(3)
    expect(page.locator('[name="done-0-description"]')).to_have_value("Premier travail")


def test_careers_tabs_and_progress_filter_round_trip(page, urls, company_a):
    sign_in(page, urls, company_a.manager)
    page.goto(urls("/carriere/"))
    tabs = page.get_by_role("navigation", name="Carrière et évaluations")

    def on(name, tab):
        def check():
            expect(page).to_have_url(re.compile(f"onglet={tab}"))
            expect(tabs.locator("[aria-current=page]")).to_contain_text(name)

        return check

    def go(name):
        return lambda: tabs.get_by_role("link", name=re.compile(name)).click()

    reviews, files = on("Entretiens", "entretiens"), on("Fiches de suivi", "fiches")
    page.goto(urls("/carriere/?onglet=entretiens"))
    round_trip(page, reviews, [(go("Fiches de suivi"), files), (go("Entretiens"), reviews)])


def test_report_tabs_round_trip(page, urls, company_a):
    sign_in(page, urls, company_a.manager)
    page.goto(urls("/interventions/?onglet=mes-comptes-rendus"))
    tabs = page.get_by_role("navigation", name="Suivi d'intervention")

    def on(name, tab):
        def check():
            expect(page).to_have_url(re.compile(f"onglet={tab}"))
            expect(tabs.locator("[aria-current=page]")).to_contain_text(name)

        return check

    def go(name):
        return lambda: tabs.get_by_role("link", name=re.compile(name)).click()

    mine, todo = on("Mes comptes rendus", "mes-comptes-rendus"), on("À valider", "a-valider")
    team = on("Mon équipe", "equipe")
    round_trip(page, mine, [(go("À valider"), todo), (go("Mon équipe"), team), (go("Mes"), mine)])
