"""Coque de l'application (docs/05-design-system.md, mise en page) : sur toutes les pages
principales, pour les 4 profils, à 6 largeurs d'écran, menu déplié et replié, dans les deux
thèmes, le document ne défile jamais, seule la zone principale défile (jamais le menu ; les
tableaux et les barres d'onglets horizontalement), la zone principale s'arrête au contenu, le
fond du menu atteint le bas de l'écran, la recherche est alignée sur le menu sans toucher le
logo, et le contenu ne dépasse pas 1 600 px. Puis le hamburger : rail
mémorisé à partir de 1 024 px, tiroir accessible en dessous."""

import re
from pathlib import Path

import pytest
from playwright.sync_api import expect

from tests.e2e.test_requests import sign_in

pytestmark = pytest.mark.django_db(transaction=True)

VIEWPORTS = [(2560, 1440), (1920, 1080), (1440, 900), (1280, 720), (1024, 768), (390, 844)]
# Menu déplié, puis replié en rail (état mémorisé, à partir de 1 024 px).
NAV_STATES = ["expanded", "collapsed"]
THEMES = ["light", "dark"]
PROFILES = ["employee", "manager", "hr", "admin"]
# Marge prévue sous le contenu (padding-bottom de .page), plus l'arrondi des mesures.
BOTTOM_MARGIN = 48 + 2

# Écarts à la règle de la coque sur la page affichée (fonction JavaScript évaluée par la page).
SHELL_PROBLEMS = (Path(__file__).parent / "shell_problems.js").read_text()


def main_pages(page, urls, company) -> list[str]:
    """Toutes les entrées du menu de la personne, plus des pages longues et des états vides."""
    page.goto(urls("/"))
    links = page.locator("#side a.nav-item").evaluate_all(
        "items => items.map(a => a.getAttribute('href'))"
    )
    review = company.requests["review"].public_id
    extras = [
        "/interventions/nouveau/",  # page longue (formulaire)
        f"/carriere/{review}/",  # page longue avec une colonne latérale
        "/annuaire/?vue=liste&q=zzzz",  # état vide
        "/carriere/?onglet=entretiens&q=zzzz",  # état vide
        "/notifications/",
    ]
    return list(dict.fromkeys([*links, *extras]))


@pytest.mark.parametrize("profile", PROFILES)
def test_only_the_main_area_scrolls_on_every_page(browser, urls, company_a, profile):
    person = getattr(company_a, profile)
    login = browser.new_context(locale="fr-FR")
    page = login.new_page()
    sign_in(page, urls, person)
    state = login.storage_state()
    paths = main_pages(page, urls, company_a)
    login.close()
    problems = []
    for width, height in VIEWPORTS:
        states = NAV_STATES if width >= 1024 else NAV_STATES[:1]
        for theme, nav in [(t, n) for t in THEMES for n in states]:
            context = browser.new_context(
                storage_state=state,
                viewport={"width": width, "height": height},
                color_scheme=theme,
                locale="fr-FR",
            )
            if nav == "collapsed":
                context.add_init_script("localStorage.setItem('dianna.nav', 'collapsed')")
            view = context.new_page()
            for path in paths:
                view.goto(urls(path), wait_until="load")
                assert view.locator("html").get_attribute("data-theme") == theme
                found = view.evaluate(SHELL_PROBLEMS, BOTTOM_MARGIN)
                problems += [f"{width}×{height} {theme} {nav} {path} : {p}" for p in found]
            context.close()
    assert problems == [], "\n".join(problems)


# ---------- Hamburger ----------


def overflow_x(page) -> bool:
    return page.evaluate(
        "() => document.documentElement.scrollWidth > innerWidth + 1"
        " || [...document.querySelectorAll('[data-main], #side, .topbar')]"
        ".some(e => e.scrollWidth > e.clientWidth + 1)"
    )


def test_desktop_burger_folds_into_a_rail_and_remembers_it(browser, urls, company_a):
    context = browser.new_context(viewport={"width": 1440, "height": 900}, locale="fr-FR")
    page = context.new_page()
    sign_in(page, urls, company_a.manager)
    page.goto(urls("/interventions/"))
    burger = page.locator("[data-nav-toggle]")
    side = page.locator("#side")
    expect(burger).to_have_attribute("aria-expanded", "true")
    expect(burger).to_have_attribute("aria-label", "Fermer le menu")
    wide = side.bounding_box()["width"]
    burger.click()
    expect(burger).to_have_attribute("aria-expanded", "false")
    expect(burger).to_have_attribute("aria-label", "Ouvrir le menu")
    expect(page.locator("#side .nav-label").first).not_to_be_in_viewport()
    rail = side.bounding_box()["width"]
    assert rail < 100 < wide
    assert page.locator("[data-main]").bounding_box()["width"] > 1440 - wide
    item = page.locator("#side a.nav-item", has_text="Annuaire")
    expect(item).to_have_attribute("title", "Annuaire")  # infobulle au survol
    assert not overflow_x(page)
    page.reload()
    expect(page.locator("html")).to_have_attribute("data-nav", "collapsed")
    assert side.bounding_box()["width"] == rail
    expect(burger).to_have_attribute("aria-expanded", "false")
    burger.click()
    expect(burger).to_have_attribute("aria-expanded", "true")
    assert side.bounding_box()["width"] == wide
    assert not overflow_x(page)
    page.reload()
    expect(page.locator("html")).not_to_have_attribute("data-nav", "collapsed")
    context.close()


def test_mobile_drawer_opens_traps_focus_and_closes_three_ways(browser, urls, company_a):
    context = browser.new_context(viewport={"width": 390, "height": 844}, locale="fr-FR")
    page = context.new_page()
    sign_in(page, urls, company_a.employee)
    page.goto(urls("/interventions/"))
    burger = page.locator("[data-nav-toggle]")
    side = page.locator("#side")
    expect(side).not_to_be_visible()
    expect(burger).to_have_attribute("aria-expanded", "false")
    expect(burger).to_have_attribute("aria-label", "Ouvrir le menu")
    expect(burger).to_have_attribute("aria-controls", "side")

    def open_drawer():
        burger.click()
        expect(side).to_be_visible()
        expect(burger).to_have_attribute("aria-expanded", "true")
        expect(burger).to_have_attribute("aria-label", "Fermer le menu")
        assert page.evaluate("() => document.activeElement.closest('#side') !== null")
        assert (
            page.evaluate("() => getComputedStyle(document.querySelector('[data-main]')).overflowY")
            == "hidden"
        )

    def closed(*, focus_on_burger=True):
        expect(side).not_to_be_visible()
        expect(burger).to_have_attribute("aria-expanded", "false")
        if focus_on_burger:
            expect(burger).to_be_focused()

    # Le focus reste dans le tiroir : Tab depuis la dernière entrée revient à la première.
    open_drawer()
    last = page.locator("#side a").last
    last.focus()
    page.keyboard.press("Tab")
    assert page.evaluate("() => document.activeElement.closest('#side') !== null")
    page.keyboard.press("Shift+Tab")
    assert page.evaluate("() => document.activeElement.closest('#side') !== null")
    # Fermeture par Échap.
    page.keyboard.press("Escape")
    closed()
    # Fermeture par le voile (à droite du tiroir).
    open_drawer()
    page.mouse.click(370, 400)
    closed()
    # Fermeture par un lien du menu : la nouvelle page s'affiche, menu fermé.
    open_drawer()
    page.locator("#side a.nav-item", has_text="Annuaire").click()
    expect(page).to_have_url(re.compile("/annuaire/"))
    closed(focus_on_burger=False)
    assert not overflow_x(page)
    context.close()
