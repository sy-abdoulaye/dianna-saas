"""Aller-retour sur les contrôles qui changent l'affichage d'une liste : chaque clic doit
changer la vue et l'adresse, et le bouton Retour doit rendre la vue précédente."""

import re

import pytest
from playwright.sync_api import expect

from tests.e2e.test_requests import sign_in

pytestmark = pytest.mark.django_db(transaction=True)


def choose(page, label):
    page.locator("form.filters fieldset.segmented label", has_text=label).click()


def test_planning_week_month_round_trip_and_back(page, urls, company_a):
    sign_in(page, urls, company_a.hr)
    page.goto(urls("/planning/"))
    table = page.locator("#planning-results table")
    expect(table).to_have_class(re.compile("plan-semaine"))
    for label, view in (
        ("Mois", "mois"),
        ("Semaine", "semaine"),
        ("Mois", "mois"),
        ("Semaine", "semaine"),
    ):
        choose(page, label)
        expect(table, f"vue affichée après « {label} » ({page.url})").to_have_class(
            re.compile(f"plan-{view}")
        )
        expect(page).to_have_url(re.compile(f"vue={view}"))
    # Retour : la vue précédente (mois), puis celle d'avant (semaine).
    page.go_back()
    expect(page).to_have_url(re.compile("vue=mois"))
    expect(page.locator("#planning-results table")).to_have_class(re.compile("plan-mois"))
    expect(page.locator("input[name=vue][value=mois]")).to_be_checked()
    page.go_back()
    expect(page).to_have_url(re.compile("vue=semaine"))
    expect(page.locator("#planning-results table")).to_have_class(re.compile("plan-semaine"))
    expect(page.locator("input[name=vue][value=semaine]")).to_be_checked()


def test_directory_list_cards_round_trip_and_back(page, urls, company_a):
    sign_in(page, urls, company_a.hr)
    page.goto(urls("/annuaire/"))
    cards, table = page.locator("#results .person-cards"), page.locator("#results table")
    expect(table).to_be_visible()
    for label, view in (
        ("Cartes", "cartes"),
        ("Liste", "liste"),
        ("Cartes", "cartes"),
        ("Liste", "liste"),
    ):
        page.locator("fieldset.segmented label", has_text=label).click()
        shown = cards if view == "cartes" else table
        expect(shown, f"affichage après « {label} » ({page.url})").to_be_visible()
        expect(page).to_have_url(re.compile(f"vue={view}"))
    page.go_back()
    expect(page).to_have_url(re.compile("vue=cartes"))
    expect(page.locator("#results .person-cards")).to_be_visible()
    expect(page.locator("input[name=vue][value=cartes]")).to_be_checked()
    page.go_back()
    expect(page).to_have_url(re.compile("vue=liste"))
    expect(page.locator("#results table")).to_be_visible()


def test_status_filter_round_trip_and_back(page, urls, company_a):
    """Liste à choix d'une barre de filtres : retour à « Tous » puis de nouveau « Validées »."""
    sign_in(page, urls, company_a.hr)
    page.goto(urls("/teletravail/?onglet=equipe"))
    status = page.get_by_label("Statut")
    for value in ("approved", "", "approved", ""):
        status.select_option(value)
        expected = f"statut={value}&|statut={value}$" if value else r"statut=(&|$)"
        expect(page, f"adresse après le statut « {value} »").to_have_url(re.compile(expected))
    page.go_back()
    expect(page).to_have_url(re.compile("statut=approved"))
    expect(page.get_by_label("Statut")).to_have_value("approved")


def test_tabs_round_trip_and_back(page, urls, company_a):
    sign_in(page, urls, company_a.hr)
    page.goto(urls("/teletravail/"))
    tabs = page.get_by_role("navigation", name="Télétravail")
    for name, tab in (
        ("À valider", "a-valider"),
        ("Mes demandes", "mes-demandes"),
        ("À valider", "a-valider"),
    ):
        tabs.get_by_role("link", name=re.compile(name)).click()
        expect(page).to_have_url(re.compile(f"onglet={tab}"))
        expect(tabs.locator("[aria-current=page]")).to_contain_text(name)
    page.go_back()
    expect(page).to_have_url(re.compile("onglet=mes-demandes"))
    expect(tabs.locator("[aria-current=page]")).to_contain_text("Mes demandes")


def test_pagination_round_trip_and_back(page, urls, company_a):
    from tests.factories import EmployeeFactory

    for index in range(12):
        EmployeeFactory(company=company_a.company, last_name=f"Zpage{index:02d}", user=None)
    sign_in(page, urls, company_a.hr)
    page.goto(urls("/annuaire/"))
    pager = page.locator("#results .pager")
    for label, number in (("Page suivante", "2"), ("Page précédente", "1"), ("Page suivante", "2")):
        pager.get_by_role("link", name=label).click()
        expect(pager.locator("[aria-current=page]")).to_have_text(number)
    expect(page).to_have_url(re.compile("page=2"))
    page.go_back()
    expect(page.locator("#results .pager [aria-current=page]")).to_have_text("1")
    page.go_back()
    expect(page.locator("#results .pager [aria-current=page]")).to_have_text("2")


def test_planning_previous_next_round_trip_and_back(page, urls, company_a):
    sign_in(page, urls, company_a.hr)
    page.goto(urls("/planning/"))
    title = page.locator(".plan-title")
    first = title.inner_text()
    page.get_by_role("link", name="Période suivante").click()
    expect(title).not_to_have_text(first)
    second = title.inner_text()
    page.get_by_role("link", name="Période précédente").click()
    expect(title).to_have_text(first)
    page.get_by_role("link", name="Période suivante").click()
    expect(title).to_have_text(second)
    page.go_back()
    expect(page.locator(".plan-title")).to_have_text(first)
