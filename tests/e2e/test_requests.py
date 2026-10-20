"""Parcours 1 et 2 de docs/08-prompts-claude-code.md et page « Module désactivé » (lot 3).
Le parcours 1 part de la page Télétravail : le planning arrive au lot 4."""

import re

import pytest
from playwright.sync_api import Page, expect

from apps.approvals.tests.conftest import next_weekday
from conftest import activate_totp, totp_code
from tests.factories import PASSWORD

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def urls(live_server):
    port = live_server.url.rsplit(":", 1)[1]
    return lambda path="/": f"http://exemple.localhost:{port}{path}"


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


def declare(page: Page, day):
    page.get_by_role("button", name="Déclarer un jour de télétravail").first.click()
    dialog = page.locator("dialog[open]")
    dialog.get_by_label("Jour").fill(day.isoformat())
    dialog.get_by_role("button", name="Envoyer la demande").click()
    return dialog


def test_employee_declares_hits_the_quota_and_cancels(page, urls, company_a, console_errors):
    # Parcours 1 : déclarer, tenter un troisième jour (quota), annuler une demande.
    sign_in(page, urls, company_a.employee)
    page.goto(urls("/teletravail/"))
    declare(page, next_weekday(weekday=1))
    expect(page.locator("#toasts .toast").last).to_contain_text("Demande envoyée")
    expect(page.locator("dialog")).to_have_count(0)
    dialog = declare(page, next_weekday(weekday=3))
    expect(
        dialog.get_by_text(
            re.compile(
                r"Vous avez déjà 2 jours de télétravail la semaine du "
                r".+ \(maximum 2\)\."
            )
        )
    ).to_be_visible()
    dialog.locator("footer").get_by_role("button", name="Annuler").click()
    row = page.locator("#results tr", has_text="En attente").first
    row.get_by_role("button", name="Annuler").click()
    page.locator("dialog[open]").get_by_role("button", name="Annuler la demande").click()
    expect(page.locator("#toasts .toast").last).to_contain_text("Demande annulée")
    expect(page.locator("#results")).to_contain_text("Annulée")
    assert console_errors == []


def test_manager_validates_one_and_refuses_another_then_employee_is_notified(
    browser, urls, company_a, submit
):
    # Parcours 2 : valider depuis « À valider », refuser avec motif ; le salarié est notifié.
    submit(company_a, company_a.employee)  # mercredi prochain (la fixture a le lundi)
    manager_context = browser.new_context(locale="fr-FR")
    page = manager_context.new_page()
    sign_in(page, urls, company_a.manager)
    expect(page.get_by_role("link", name=re.compile("Télétravail"))).to_contain_text("2")
    page.goto(urls("/teletravail/?onglet=a-valider"))
    rows = page.locator("#results tbody tr")
    expect(rows).to_have_count(2)
    rows.first.get_by_role("button", name="Valider").click()
    expect(page.locator("#toasts .toast").last).to_contain_text("Demande validée")
    expect(page.locator("#results tbody tr")).to_have_count(1)
    page.locator("#results tbody tr").first.get_by_role("button", name="Refuser").click()
    dialog = page.locator("dialog[open]")
    dialog.get_by_role("button", name="Refuser la demande").click()
    expect(dialog.get_by_text("Indiquez le motif du refus.").first).to_be_visible()
    dialog.get_by_label("Motif du refus").fill("Réunion d'équipe ce jour-là")
    dialog.get_by_role("button", name="Refuser la demande").click()
    expect(page.get_by_text("Rien à valider")).to_be_visible()
    manager_context.close()

    employee_context = browser.new_context(locale="fr-FR")
    page = employee_context.new_page()
    sign_in(page, urls, company_a.employee)
    page.get_by_role("button", name=re.compile(r"Notifications, \d+ non lues")).click()
    menu = page.locator("#menu-notifications")
    expect(menu).to_contain_text("a été validée")
    expect(menu).to_contain_text("Réunion d'équipe ce jour-là")
    employee_context.close()


def test_undo_from_the_notification_after_a_validation(page, urls, company_a):
    sign_in(page, urls, company_a.manager)
    page.goto(urls("/teletravail/?onglet=a-valider"))
    page.locator("#results tbody tr").first.get_by_role("button", name="Valider").click()
    toast = page.locator("#toasts .toast").last
    toast.get_by_role("button", name="Annuler").click()
    expect(page.locator("#toasts .toast").last).to_contain_text("Décision annulée")
    expect(page.locator("#results tbody tr")).to_have_count(1)


def test_disabled_module_page(page, urls, company_a):
    sign_in(page, urls, company_a.admin)
    page.goto(urls("/administration/modules/"))
    page.get_by_role("checkbox", name=re.compile("Astreintes")).uncheck()
    page.locator("dialog[open]").get_by_role("button", name="Désactiver").click()
    expect(page.get_by_role("checkbox", name=re.compile("Astreintes"))).not_to_be_checked()
    expect(page.locator("#side")).not_to_contain_text("Astreintes")
    page.goto(urls("/astreintes/"))
    expect(page.get_by_role("heading", name="Module désactivé")).to_be_visible()
    expect(page.get_by_text("Vous pouvez le réactiver dans Administration.")).to_be_visible()
