"""Parcours 4 (RH) et 5 (Administrateur) de docs/08-prompts-claude-code.md, recherche
globale et fiche (lot 2)."""

import re

import pytest
from playwright.sync_api import Page, expect

from conftest import activate_totp, totp_code
from tests.factories import PASSWORD

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def urls(live_server):
    port = live_server.url.rsplit(":", 1)[1]

    def _url(path: str = "/", host: str = "exemple") -> str:
        return f"http://{host}.localhost:{port}{path}"

    return _url


def sign_in(page: Page, urls, person):
    secret = activate_totp(person.user) if person.requires_two_factor else None
    page.goto(urls("/connexion/"))
    page.get_by_label("E-mail").fill(person.email)
    page.get_by_label("Mot de passe").fill(PASSWORD)
    page.get_by_role("button", name="Se connecter").click()
    if secret:
        page.get_by_label("Code").fill(totp_code(secret))
        page.get_by_role("button", name="Valider").click()
    expect(page.get_by_role("heading", level=1)).to_contain_text("Bonjour")


def test_hr_creates_with_duplicate_email_fixes_archives_and_undoes(
    page, urls, company_a, console_errors
):
    # Parcours 4 : adresse déjà utilisée (erreur), correction, archivage, annulation.
    sign_in(page, urls, company_a.hr)
    page.goto(urls("/annuaire/"))
    page.get_by_role("link", name="Ajouter un collaborateur").click()
    page.get_by_label("Prénom").fill("Ada")
    page.locator("#id_last_name").fill("Lovelace")
    page.get_by_label("E-mail professionnel").fill(company_a.manager.email)
    page.get_by_label("Intitulé du poste").fill("Analyste")
    page.get_by_label("Service").select_option(label="Support client")
    page.get_by_label("Site").select_option(label="Lyon")
    page.get_by_label("Date d'arrivée").fill("2024-01-08")
    page.get_by_role("button", name="Créer la fiche").click()
    expect(page.get_by_role("alert")).to_contain_text("1 information est à corriger.")
    expect(
        page.get_by_text(f"Cette adresse est déjà utilisée par {company_a.manager.full_name}.")
    ).to_be_visible()
    expect(page.get_by_label("Intitulé du poste")).to_have_value("Analyste")
    page.get_by_label("E-mail professionnel").fill("ada.lovelace@exemple.fr")
    page.get_by_role("button", name="Créer la fiche").click()
    expect(page.get_by_role("heading", level=1)).to_have_text("Ada Lovelace")
    expect(page.locator("#toasts")).to_contain_text("Fiche créée")

    page.get_by_role("button", name="Archiver", exact=True).click()
    dialog = page.locator("dialog[open]")
    expect(dialog.get_by_role("heading")).to_have_text("Archiver Ada Lovelace ?")
    dialog.get_by_role("button", name="Archiver la fiche").click()
    toast = page.locator("#toasts .toast").last
    expect(toast).to_contain_text("Fiche archivée")
    expect(page.locator("#person")).to_contain_text("Parti")
    toast.get_by_role("button", name="Annuler").click()
    expect(page.locator("#toasts .toast").last).to_contain_text("Archivage annulé")
    expect(page.locator("#person")).to_contain_text("Actif")
    assert console_errors == []


def test_admin_cannot_delete_a_used_service_and_disables_a_module(page, urls, company_a):
    # Parcours 5 : suppression d'un service utilisé, désactivation d'un module.
    sign_in(page, urls, company_a.admin)
    page.goto(urls("/administration/structure/"))
    page.get_by_role("button", name="Supprimer Support client").click()
    dialog = page.locator("dialog[open]")
    expect(dialog.get_by_role("heading")).to_have_text("Suppression impossible")
    expect(dialog).to_contain_text("est utilisé par")
    dialog.locator("footer").get_by_role("button", name="Fermer").click()

    page.goto(urls("/administration/modules/"))
    checkbox = page.get_by_role("checkbox", name=re.compile("Questionnaires"))
    checkbox.uncheck()
    dialog = page.locator("dialog[open]")
    expect(dialog).to_contain_text("Le module disparaîtra du menu de tous les utilisateurs.")
    dialog.get_by_role("button", name="Annuler").click()
    expect(page.get_by_role("checkbox", name=re.compile("Questionnaires"))).to_be_checked()
    page.get_by_role("checkbox", name=re.compile("Questionnaires")).uncheck()
    page.locator("dialog[open]").get_by_role("button", name="Désactiver").click()
    expect(page.get_by_role("checkbox", name=re.compile("Questionnaires"))).not_to_be_checked()


def test_admin_changes_a_profile_with_confirmation(page, urls, company_a):
    sign_in(page, urls, company_a.admin)
    page.goto(urls("/administration/utilisateurs/"))
    select = page.get_by_label(f"Profil de {company_a.employee.full_name}")
    select.select_option("manager")
    dialog = page.locator("dialog[open]")
    expect(dialog).to_contain_text("Salarié → Manager")
    dialog.get_by_role("button", name="Changer le profil").click()
    expect(page.locator("#toasts .toast").last).to_contain_text("Profil modifié")
    expect(page.get_by_label(f"Profil de {company_a.employee.full_name}")).to_have_value("manager")
    own = page.get_by_label(f"Profil de {company_a.admin.full_name}")
    expect(own).to_be_disabled()


def test_global_search_and_my_record(page, urls, company_a):
    sign_in(page, urls, company_a.employee)
    page.get_by_label("Recherche globale").fill(company_a.manager.last_name[:4])
    suggestion = page.locator("#search-suggestions").get_by_role(
        "link", name=re.compile(company_a.manager.full_name)
    )
    suggestion.click()
    expect(page.get_by_role("heading", level=1)).to_have_text(company_a.manager.full_name)
    page.get_by_role("button", name=company_a.employee.full_name).click()
    page.get_by_role("link", name="Ma fiche").click()
    expect(page.get_by_text("Visible par vous et les RH")).to_be_visible()
    page.get_by_role("button", name="Modifier mes coordonnées").click()
    dialog = page.locator("dialog[open]")
    dialog.get_by_label("Téléphone professionnel").fill("12")
    dialog.get_by_role("button", name="Enregistrer").click()
    expect(dialog.get_by_text("Saisissez un numéro valide (au moins 8 chiffres).")).to_be_visible()
    dialog.get_by_label("Téléphone professionnel").fill("04 72 00 00 00")
    dialog.get_by_role("button", name="Enregistrer").click()
    expect(page.locator("#person")).to_contain_text("04 72 00 00 00")


def test_directory_filters_and_cards(page, urls, company_a):
    sign_in(page, urls, company_a.employee)
    page.goto(urls("/annuaire/"))
    page.get_by_label("Recherche", exact=True).fill("zzzz")
    expect(page.get_by_text("Aucun collaborateur trouvé")).to_be_visible()
    expect(page).to_have_url(re.compile(r"q=zzzz"))
    page.get_by_role("link", name="Réinitialiser les filtres").click()
    expect(page).not_to_have_url(re.compile(r"q=zzzz"))
    page.locator("label").filter(has_text="Cartes").click()
    expect(page.locator(".person-card").first).to_be_visible()
    # L'adresse « Cartes » doit être dans l'historique avant de revenir en arrière.
    expect(page).to_have_url(re.compile(r"vue=cartes"))
    page.go_back()
    expect(page).not_to_have_url(re.compile(r"vue=cartes"))
    expect(page.get_by_role("heading", level=1)).to_have_text("Annuaire")
    page.go_back()
    expect(page).to_have_url(re.compile(r"q=zzzz"))
