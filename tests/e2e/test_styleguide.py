"""Guide de style : thème, modales, notifications, erreurs, filtres, mobile (lot 0)."""

import re

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.django_db(transaction=True)


def open_styleguide(page: Page, url: str):
    page.goto(url)
    expect(page.get_by_role("heading", level=1, name="Guide de style")).to_be_visible()


def test_page_loads_without_console_or_csp_errors(page, styleguide_url, console_errors):
    open_styleguide(page, styleguide_url)
    page.locator("dialog").count()
    assert console_errors == []


def test_theme_choice_is_applied_and_remembered(page, styleguide_url):
    open_styleguide(page, styleguide_url)
    html = page.locator("html")
    expect(html).to_have_attribute("data-theme", "light")
    page.get_by_role("button", name="Camille Durand").click()
    page.locator("#menu-user").get_by_label("Sombre").check()
    expect(html).to_have_attribute("data-theme", "dark")
    page.reload()
    expect(html).to_have_attribute("data-theme", "dark")
    expect(html).to_have_attribute("data-theme-pref", "dark")


def test_system_theme_follows_the_operating_system(page, styleguide_url):
    page.emulate_media(color_scheme="dark")
    open_styleguide(page, styleguide_url)
    expect(page.locator("html")).to_have_attribute("data-theme", "dark")
    page.emulate_media(color_scheme="light")
    expect(page.locator("html")).to_have_attribute("data-theme", "light")


def test_modal_keyboard_focus_and_escape(page, styleguide_url):
    open_styleguide(page, styleguide_url)
    opener = page.locator("#modals").get_by_role("button", name="Formulaire en modale")
    opener.click()
    dialog = page.locator("dialog[open]")
    expect(dialog).to_be_visible()
    expect(dialog.get_by_label("Jour")).to_be_focused()
    page.keyboard.press("Escape")
    expect(page.locator("dialog")).to_have_count(0)
    expect(opener).to_be_focused()


def test_modal_closes_with_cancel_and_close_buttons(page, styleguide_url):
    open_styleguide(page, styleguide_url)
    opener = page.locator("#modals").get_by_role("button", name="Formulaire en modale")
    opener.click()
    page.locator("dialog").get_by_role("button", name="Annuler").click()
    expect(page.locator("dialog")).to_have_count(0)
    opener.click()
    page.locator("dialog").get_by_role("button", name="Fermer").click()
    expect(page.locator("dialog")).to_have_count(0)


def test_form_errors_keep_input_then_success_toast_and_undo(page, styleguide_url):
    open_styleguide(page, styleguide_url)
    page.locator("#modals").get_by_role("button", name="Formulaire en modale").click()
    dialog = page.locator("dialog[open]")
    dialog.get_by_label("Jour").fill("2026-10-24")
    dialog.get_by_label("Commentaire").fill("Rendez-vous médical")
    dialog.get_by_role("button", name="Envoyer la demande").click()
    expect(dialog.get_by_role("alert")).to_contain_text("1 information est à corriger.")
    expect(dialog.get_by_text("Le télétravail se déclare du lundi au vendredi.")).to_be_visible()
    day = dialog.get_by_label("Jour")
    expect(day).to_have_attribute("aria-invalid", "true")
    expect(day).to_be_focused()
    expect(dialog.get_by_label("Commentaire")).to_have_value("Rendez-vous médical")

    day.fill("2026-10-22")
    dialog.get_by_role("button", name="Envoyer la demande").click()
    expect(page.locator("dialog")).to_have_count(0)
    toast = page.locator("#toasts .toast").last
    expect(toast).to_contain_text("Demande envoyée")
    expect(toast.locator("b", has_text="Louise Martin")).to_be_visible()
    toast.get_by_role("button", name="Annuler").click()
    expect(page.locator("#toasts .toast").last).to_contain_text("Action annulée")


def test_undo_after_the_window_shows_too_late(page, styleguide_url, settings):
    settings.UNDO_WINDOW_SECONDS = -1
    open_styleguide(page, styleguide_url)
    page.locator("#modals").get_by_role("button", name="Formulaire en modale").click()
    dialog = page.locator("dialog[open]")
    dialog.get_by_label("Jour").fill("2026-10-22")
    dialog.get_by_role("button", name="Envoyer la demande").click()
    page.locator("#toasts .toast").last.get_by_role("button", name="Annuler").click()
    expect(page.locator("#toasts .toast-err")).to_contain_text(
        "Il est trop tard pour annuler cette action."
    )


def test_destructive_confirmation(page, styleguide_url):
    open_styleguide(page, styleguide_url)
    page.locator("#modals").get_by_role("button", name="Confirmation destructive").click()
    dialog = page.locator("dialog[open]")
    expect(dialog.get_by_role("heading", name="Archiver la fiche ?")).to_be_visible()
    dialog.get_by_role("button", name="Archiver").click()
    expect(page.locator("dialog")).to_have_count(0)
    expect(page.locator("#toasts .toast").last).to_contain_text("Fiche archivée")


def test_at_most_three_toasts(page, styleguide_url):
    open_styleguide(page, styleguide_url)
    section = page.locator("#toasts-demo")
    for name in ["Succès", "Information", "Avertissement", "Erreur"]:
        section.get_by_role("button", name=name, exact=True).click()
        page.wait_for_timeout(150)
    expect(page.locator("#toasts .toast")).to_have_count(3)
    expect(page.locator("#toasts .toast").last).to_have_attribute("role", "alert")


def test_server_error_banner_keeps_the_input(page, styleguide_url):
    open_styleguide(page, styleguide_url)
    form = page.locator("#toasts-demo form")
    form.get_by_label("Texte saisi").fill("Ma saisie importante")
    form.get_by_role("button", name="Enregistrer").click()
    expect(form.get_by_role("alert")).to_contain_text("Le serveur n'a pas répondu.")
    expect(form.get_by_label("Texte saisi")).to_have_value("Ma saisie importante")


def test_filters_update_results_and_url(page, styleguide_url):
    open_styleguide(page, styleguide_url)
    table = page.locator("#table")
    table.get_by_label("Recherche").fill("zzzz")
    expect(table.get_by_text("Aucun collaborateur trouvé")).to_be_visible()
    expect(page).to_have_url(re.compile(r"q=zzzz"))
    table.get_by_role("link", name="Réinitialiser", exact=True).click()
    expect(table.get_by_text("1 à 8 sur 24")).to_be_visible()
    expect(table.get_by_label("Recherche")).to_have_value("")
    table.get_by_role("navigation", name="Pagination").get_by_role("link", name="2").click()
    expect(table.get_by_text("9 à 16 sur 24")).to_be_visible()
    expect(page).to_have_url(re.compile(r"page=2"))


def test_mobile_drawer_and_no_horizontal_scroll(page, styleguide_url):
    page.set_viewport_size({"width": 375, "height": 812})
    open_styleguide(page, styleguide_url)
    burger = page.get_by_role("button", name="Ouvrir le menu")
    expect(page.locator("#side")).not_to_be_in_viewport()
    burger.click()
    expect(burger).to_have_attribute("aria-expanded", "true")
    expect(page.locator("#side")).to_be_in_viewport()
    page.keyboard.press("Escape")
    expect(burger).to_have_attribute("aria-expanded", "false")
    expect(burger).to_be_focused()
    overflow = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
    assert overflow <= 0


def test_skip_link_moves_focus_to_content(page, styleguide_url):
    open_styleguide(page, styleguide_url)
    page.keyboard.press("Tab")
    skip = page.get_by_role("link", name="Aller au contenu")
    expect(skip).to_be_focused()
    page.keyboard.press("Enter")
    expect(page.locator("#content")).to_be_focused()


def test_toasts_stay_visible_and_clickable_above_an_open_modal(page, styleguide_url):
    open_styleguide(page, styleguide_url)
    page.locator("#toasts-demo").get_by_role("button", name="Succès", exact=True).click()
    page.locator("#modals").get_by_role("button", name="Confirmation", exact=True).click()
    dialog = page.locator("dialog[open]")
    expect(dialog.locator("#toasts .toast")).to_have_count(1)
    dialog.get_by_role("button", name="Marquer comme réalisé").click()
    expect(page.locator("dialog")).to_have_count(0)
    expect(page.locator("body > #toasts .toast").last).to_contain_text(
        "Entretien marqué comme réalisé"
    )
