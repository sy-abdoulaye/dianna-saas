"""Aller-retour sur les contrôles qui changent l'affichage d'une liste : chaque clic doit
changer la vue et l'adresse, et le bouton Retour doit rendre la vue précédente."""

import re

import pytest
from playwright.sync_api import expect

from tests.e2e.test_requests import sign_in

pytestmark = pytest.mark.django_db(transaction=True)


def choose(page, label):
    page.locator("form.filters fieldset.segmented label", has_text=label).click()


def round_trip(page, start, steps):
    """Gabarit commun des parcours aller-retour : `start` vérifie l'état de départ, chaque
    étape est un couple (clic, vérification). Après les clics, Retour jusqu'au départ en
    vérifiant chaque état précédent, puis Suivant jusqu'au dernier."""
    states = [start]
    start()
    for click, check in steps:
        click()
        check()
        states.append(check)
    for check in reversed(states[:-1]):
        page.go_back()
        check()
    for check in states[1:]:
        page.go_forward()
        check()


WEEK = "Semaine du 26 oct. au 1er novembre 2026"


def planning_shows(page, view, title):
    def check():
        expect(page, f"adresse de la vue {view}").to_have_url(re.compile(f"vue={view}"))
        expect(page.locator("#planning-results table")).to_have_class(re.compile(f"plan-{view}"))
        expect(page.locator(".plan-title")).to_have_text(title)
        expect(page.locator(f"input[name=vue][value={view}]")).to_be_checked()

    return check


def test_planning_week_month_round_trip_and_back(page, urls, company_a):
    """La période de référence est gardée : Semaine, Mois, Semaine revient à la même semaine."""
    sign_in(page, urls, company_a.hr)
    page.goto(urls("/planning/?vue=semaine&date=2026-10-28"))
    week, month = (
        planning_shows(page, "semaine", WEEK),
        planning_shows(page, "mois", "octobre 2026"),
    )
    round_trip(
        page,
        week,
        [
            (lambda: choose(page, "Mois"), month),
            (lambda: choose(page, "Semaine"), week),
            (lambda: choose(page, "Mois"), month),
            (lambda: choose(page, "Semaine"), week),
        ],
    )


def test_planning_previous_next_round_trip_and_back(page, urls, company_a):
    sign_in(page, urls, company_a.hr)
    page.goto(urls("/planning/?vue=semaine&date=2026-10-28"))

    def period(title):
        return lambda: expect(page.locator(".plan-title")).to_have_text(title)

    def go(name):
        return lambda: page.get_by_role("link", name=name).click()

    following = "Semaine du 2 nov. au 8 novembre 2026"
    round_trip(
        page,
        period(WEEK),
        [
            (go("Période suivante"), period(following)),
            (go("Période précédente"), period(WEEK)),
            (go("Période suivante"), period(following)),
        ],
    )


def test_directory_list_cards_round_trip_and_back(page, urls, company_a):
    sign_in(page, urls, company_a.hr)
    page.goto(urls("/annuaire/"))

    def shows(view):
        def check():
            shown = "#results .person-cards" if view == "cartes" else "#results table"
            expect(page.locator(shown), f"affichage {view}").to_be_visible()
            expect(page.locator(f"input[name=vue][value={view}]")).to_be_checked()

        return check

    def pick(label):
        return lambda: page.locator("fieldset.segmented label", has_text=label).click()

    round_trip(
        page,
        shows("liste"),
        [
            (pick("Cartes"), shows("cartes")),
            (pick("Liste"), shows("liste")),
            (pick("Cartes"), shows("cartes")),
            (pick("Liste"), shows("liste")),
        ],
    )


def test_status_filter_round_trip_and_back(page, urls, company_a):
    """Liste à choix d'une barre de filtres : retour à « Tous » puis de nouveau « Validées »."""
    sign_in(page, urls, company_a.hr)
    page.goto(urls("/teletravail/?onglet=equipe"))

    def status(value):
        def check():
            expected = f"statut={value}(&|$)" if value else r"statut=(&|$)|^[^?]*\?(?!.*statut=)"
            expect(page, f"adresse du statut « {value} »").to_have_url(re.compile(expected))
            expect(page.get_by_label("Statut")).to_have_value(value)

        return check

    def select(value):
        return lambda: page.get_by_label("Statut").select_option(value)

    round_trip(
        page,
        status(""),
        [
            (select("approved"), status("approved")),
            (select(""), status("")),
            (select("approved"), status("approved")),
        ],
    )


def test_tabs_round_trip_and_back(page, urls, company_a):
    sign_in(page, urls, company_a.hr)
    page.goto(urls("/teletravail/?onglet=mes-demandes"))
    tabs = page.get_by_role("navigation", name="Télétravail")

    def current(name, tab):
        def check():
            expect(page).to_have_url(re.compile(f"onglet={tab}"))
            expect(tabs.locator("[aria-current=page]")).to_contain_text(name)

        return check

    def open_tab(name):
        return lambda: tabs.get_by_role("link", name=re.compile(name)).click()

    to_validate, mine = current("À valider", "a-valider"), current("Mes demandes", "mes-demandes")
    round_trip(
        page,
        mine,
        [
            (open_tab("À valider"), to_validate),
            (open_tab("Mes demandes"), mine),
            (open_tab("À valider"), to_validate),
        ],
    )


def test_pagination_round_trip_and_back(page, urls, company_a):
    from tests.factories import EmployeeFactory

    for index in range(12):
        EmployeeFactory(company=company_a.company, last_name=f"Zpage{index:02d}", user=None)
    sign_in(page, urls, company_a.hr)
    page.goto(urls("/annuaire/?vue=liste"))
    pager = page.locator("#results .pager")

    def on(number):
        return lambda: expect(page.locator("#results .pager [aria-current=page]")).to_have_text(
            number
        )

    def follow(label):
        return lambda: pager.get_by_role("link", name=label).click()

    round_trip(
        page,
        on("1"),
        [
            (follow("Page suivante"), on("2")),
            (follow("Page précédente"), on("1")),
            (follow("Page suivante"), on("2")),
        ],
    )


def back_and_forward_show_the_whole_page(page, url_part, heading):
    """Après une action, Retour puis Suivant : la page entière revient (jamais un fragment
    nu tiré du cache du navigateur, Vary: HX-Request et Cache-Control: no-store)."""
    page.go_back()
    expect(page).not_to_have_url(re.compile(re.escape(url_part)))
    page.go_forward()
    expect(page).to_have_url(re.compile(re.escape(url_part)))
    expect(page.get_by_role("heading", level=1)).to_contain_text(heading)
    expect(page.get_by_role("button", name=re.compile("Notifications"))).to_be_visible()
    expect(page.locator("main#content")).to_have_count(1)


def test_telework_action_then_back_and_forward(page, urls, company_a):
    from apps.approvals.tests.conftest import next_weekday
    from tests.e2e.test_requests import declare

    sign_in(page, urls, company_a.employee)
    page.goto(urls("/teletravail/"))
    declare(page, next_weekday(weekday=1))
    expect(page.locator("#toasts .toast").last).to_contain_text("Demande envoyée")
    expect(page.locator("#results")).to_contain_text("En attente")
    back_and_forward_show_the_whole_page(page, "/teletravail/", "Télétravail")
    expect(page.locator("#results")).to_contain_text("En attente")


def test_validation_action_then_back_and_forward(page, urls, company_a, submit):
    submit(company_a, company_a.employee)
    sign_in(page, urls, company_a.manager)
    page.goto(urls("/teletravail/?onglet=a-valider"))
    page.locator("#results tbody tr").first.get_by_role("button", name="Valider").click()
    expect(page.locator("#toasts .toast").last).to_contain_text("Demande validée")
    expect(page.locator("#results tbody tr")).to_have_count(1)
    back_and_forward_show_the_whole_page(page, "onglet=a-valider", "Télétravail")
    expect(page.locator("#results tbody tr")).to_have_count(1)


def test_closure_action_then_back_and_forward(page, urls, company_a):
    sign_in(page, urls, company_a.admin)
    page.goto(urls("/administration/fermetures/"))
    page.get_by_role("button", name="Ajouter une fermeture").click()
    dialog = page.locator("dialog[open]")
    dialog.get_by_label("Date").fill("2031-05-30")
    dialog.get_by_label("Libellé").fill("Pont de l'Ascension")
    dialog.get_by_role("button", name="Ajouter").click()
    expect(page.locator("#content")).to_contain_text("Pont de l'Ascension")
    back_and_forward_show_the_whole_page(page, "/administration/fermetures/", "Administration")
    expect(page.locator("#content")).to_contain_text("Pont de l'Ascension")


def test_park_status_filter_round_trip_and_back(page, urls, company_a):
    """Filtre « État » du parc : Retour et Suivant rendent la valeur portée par l'adresse."""
    sign_in(page, urls, company_a.hr)
    page.goto(urls("/materiel/?onglet=parc"))
    status = page.get_by_label("État")

    def shows(value):
        def check():
            expect(page).to_have_url(re.compile(f"etat={value}(&|$)" if value else "onglet=parc"))
            expect(page.get_by_label("État")).to_have_value(value)

        return check

    def select(value):
        def submit():
            status.select_option(value)
            page.get_by_role("button", name="Filtrer").click()  # formulaire classique

        return submit

    round_trip(
        page,
        shows(""),
        [
            (select("in_stock"), shows("in_stock")),
            (select("repair"), shows("repair")),
            (select(""), shows("")),
        ],
    )
