"""Navigation unique après une action (R1-02) : la page n'est jamais rechargée entièrement
(sauf l'activation d'un module) ; la notification visuelle reste à l'écran."""

import pytest
from playwright.sync_api import expect

from tests.e2e.test_requests import sign_in

pytestmark = pytest.mark.django_db(transaction=True)


def mark_document(page):
    """Marqueur posé dans le document : il disparaît si la page est rechargée."""
    page.evaluate("window.__sameDocument = true")


def test_saving_company_settings_reloads_only_the_page_zone(page, urls, company_a):
    sign_in(page, urls, company_a.admin)
    page.goto(urls("/administration/"))
    mark_document(page)
    page.get_by_label("Nom de l'entreprise").fill("Exemple SAS (siège)")
    page.get_by_role("button", name="Enregistrer").click()
    expect(page.locator("#toasts .toast").last).to_contain_text("Paramètres enregistrés")
    expect(page.get_by_label("Nom de l'entreprise")).to_have_value("Exemple SAS (siège)")
    assert page.evaluate("window.__sameDocument") is True


def test_creating_a_record_goes_to_its_page_without_reloading_the_document(page, urls, company_a):
    sign_in(page, urls, company_a.hr)
    page.goto(urls("/annuaire/nouveau/"))
    mark_document(page)
    page.get_by_label("Prénom").fill("Ada")
    page.locator("#id_last_name").fill("Lovelace")
    page.get_by_label("E-mail professionnel").fill("ada.lovelace@exemple.fr")
    page.get_by_label("Intitulé du poste").fill("Analyste")
    page.get_by_label("Service").select_option(label="Support client")
    page.get_by_label("Site").select_option(label="Lyon")
    page.get_by_label("Date d'arrivée").fill("2024-01-08")
    page.get_by_role("button", name="Créer la fiche").click()
    expect(page.get_by_role("heading", level=1)).to_have_text("Ada Lovelace")
    expect(page.locator("#toasts .toast").last).to_contain_text("Fiche créée")
    assert "/annuaire/" in page.url and page.url.rstrip("/").split("/")[-1] != "nouveau"
    assert page.evaluate("window.__sameDocument") is True
