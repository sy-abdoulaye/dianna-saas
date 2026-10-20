"""Parcours du lot 4 : parcours 1 depuis le planning, export du planning, tableau de bord."""

import re
from datetime import timedelta

import pytest
from playwright.sync_api import Page, expect

from apps.approvals.tests.conftest import next_weekday
from tests.e2e.test_requests import sign_in

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def urls(live_server):
    port = live_server.url.rsplit(":", 1)[1]
    return lambda path="/": f"http://exemple.localhost:{port}{path}"


def open_week(page: Page, urls, monday):
    page.goto(urls(f"/planning/?date={monday.isoformat()}"))
    expect(page.get_by_role("heading", level=1)).to_have_text("Planning")


def test_employee_declares_from_the_planning_then_hits_the_quota(
    page, urls, company_a, console_errors
):
    # Parcours 1 depuis le planning : clic sur une journée « Sur site » → modale pré-remplie.
    monday = next_weekday()
    tuesday, thursday = monday + timedelta(days=1), monday + timedelta(days=3)
    sign_in(page, urls, company_a.employee)
    open_week(page, urls, monday)
    page.get_by_role("button", name=re.compile(r"Sur site\. Déclarer du télétravail")).first.click()
    dialog = page.locator("dialog[open]")
    expect(dialog.get_by_label("Jour")).to_have_value(tuesday.isoformat())
    dialog.get_by_role("button", name="Envoyer la demande").click()
    expect(page.locator("#toasts .toast").last).to_contain_text("Demande envoyée")
    # Le planning se met à jour : deux jours de télétravail en attente (hachurés).
    expect(page.locator("#planning-results .cell.k-tt.pend")).to_have_count(2)
    # Troisième jour la même semaine : erreur de quota.
    page.locator(f'button[hx-get$="date={thursday.isoformat()}"]').click()
    dialog = page.locator("dialog[open]")
    dialog.get_by_role("button", name="Envoyer la demande").click()
    expect(dialog.get_by_text(re.compile(r"Vous avez déjà 2 jours de télétravail"))).to_be_visible()
    assert console_errors == []


def test_month_view_navigation_and_filters(page, urls, company_a, console_errors):
    sign_in(page, urls, company_a.hr)
    page.goto(urls("/planning/?date=2026-10-21"))
    expect(page.locator(".plan-title")).to_have_text("Semaine du 19 oct. au 25 octobre 2026")
    page.get_by_role("radio", name="Mois").check()
    expect(page.locator(".plan-title")).to_have_text("octobre 2026")
    page.get_by_role("link", name="Période suivante").click()
    expect(page.locator(".plan-title")).to_have_text("novembre 2026")
    page.get_by_role("searchbox", name="Recherche", exact=True).fill("Louise")
    expect(page.locator("#planning-results tbody tr")).to_have_count(1)
    expect(page.locator("#planning-results")).to_contain_text("Louise")
    assert console_errors == []


def test_hr_exports_the_planning_to_csv(page, urls, company_a, console_errors):
    sign_in(page, urls, company_a.hr)
    page.goto(urls("/planning/"))
    page.get_by_role("link", name="Exporter").click()
    expect(page.get_by_role("heading", level=1)).to_have_text("Export du planning")
    page.get_by_role("button", name="Générer l'export").click()
    expect(page.get_by_text("Aperçu de l'export")).to_be_visible()
    with page.expect_download() as info:
        page.get_by_role("link", name="Télécharger le fichier CSV").click()
    assert info.value.suggested_filename.startswith("planning-")
    assert info.value.suggested_filename.endswith(".csv")
    # Période de 4 mois : refusée avec le message de la fiche.
    page.get_by_label("Période", exact=False).first.select_option("personnalisee")
    page.get_by_label("Du (période personnalisée)").fill("2026-11-02")
    page.get_by_label("Au (période personnalisée)").fill("2027-03-01")
    page.get_by_role("button", name="Générer l'export").click()
    expect(page.get_by_text("La période est limitée à 3 mois par export.")).to_be_visible()
    assert console_errors == []


def test_dashboard_today_block_leads_to_the_planning(page, urls, company_a, console_errors):
    sign_in(page, urls, company_a.manager)
    expect(page.get_by_role("heading", name="À traiter")).to_be_visible()
    expect(page.get_by_text("1 demande de télétravail à valider")).to_be_visible()
    page.get_by_role("link", name="Voir le planning").click()
    expect(page.get_by_role("heading", level=1)).to_have_text("Planning")
    assert console_errors == []
