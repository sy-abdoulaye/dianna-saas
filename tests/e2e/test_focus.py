"""Focus après une action ou la fermeture d'une modale (WCAG 2.4.3) : il revient au bouton
d'origine, ou au premier élément utile de la zone rechargée si ce bouton a disparu."""

import re

import pytest
from playwright.sync_api import expect

from tests.e2e.test_requests import sign_in

pytestmark = pytest.mark.django_db(transaction=True)

FOCUS_LOST = "() => !document.activeElement || document.activeElement === document.body"


def focused_inside(page, selector):
    return page.evaluate(f"() => Boolean(document.activeElement.closest({selector!r}))")


def test_focus_goes_to_the_next_useful_element_when_the_button_disappears(
    page, urls, company_a, submit
):
    submit(company_a, company_a.employee)
    sign_in(page, urls, company_a.manager)
    page.goto(urls("/teletravail/?onglet=a-valider"))
    page.locator("#results tbody tr").first.get_by_role("button", name="Valider").click()
    expect(page.locator("#results tbody tr")).to_have_count(1)
    page.wait_for_function(f"() => !({FOCUS_LOST})()")
    assert focused_inside(page, "#results")


def test_focus_comes_back_after_a_modal_action_reloads_the_list(page, urls, company_a, submit):
    submit(company_a, company_a.employee)
    sign_in(page, urls, company_a.manager)
    page.goto(urls("/teletravail/?onglet=a-valider"))
    page.locator("#results tbody tr").first.get_by_role("button", name="Refuser").click()
    dialog = page.locator("dialog[open]")
    dialog.get_by_label("Motif du refus").fill("Réunion d'équipe")
    dialog.get_by_role("button", name="Refuser la demande").click()
    expect(page.locator("dialog")).to_have_count(0)
    expect(page.locator("#results tbody tr")).to_have_count(1)
    page.wait_for_function(f"() => !({FOCUS_LOST})()")
    assert focused_inside(page, "#content")


def test_closing_a_modal_gives_the_focus_back_to_its_button(page, urls, company_a):
    sign_in(page, urls, company_a.admin)
    page.goto(urls("/administration/fermetures/"))
    opener = page.get_by_role("button", name="Ajouter une fermeture")
    opener.click()
    page.locator("dialog[open]").get_by_role("button", name="Annuler").click()
    expect(page.locator("dialog")).to_have_count(0)
    expect(opener).to_be_focused()


def test_the_export_modal_closes_after_the_download(page, urls, company_a):
    sign_in(page, urls, company_a.hr)
    page.goto(urls("/teletravail/"))
    opener = page.get_by_role("button", name="Exporter")
    opener.click()
    dialog = page.locator("dialog[open]")
    dialog.locator("label.checkbox").first.click()
    with page.expect_download() as download:
        dialog.get_by_role("button", name="Télécharger").click()
    assert re.search(r"\.(csv|xlsx|pdf)$", download.value.suggested_filename)
    expect(page.locator("dialog")).to_have_count(0)
    expect(opener).to_be_focused()
