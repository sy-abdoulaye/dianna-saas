"""Coque de l'application (docs/05-design-system.md, mise en page) : sur toutes les pages
principales, pour les 4 profils, à 6 largeurs d'écran, menu déplié et replié, dans les deux
thèmes, le document défile et s'arrête au contenu, aucun autre défilement que le menu (sans
barre visible), les tableaux et les barres d'onglets, le menu collant atteint le bas de
l'écran, la recherche est alignée sur le menu sans toucher le logo et le contenu ne dépasse
pas 1 600 px. Puis : chaque entrée du menu est atteignable et cliquable sur les écrans peu
hauts et avec un zoom de 200 %, la position est rendue après Retour, et le hamburger replie le
menu en rail (≥ 1 024 px) ou l'ouvre en tiroir accessible."""

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
        # La page ne défile pas derrière le tiroir.
        assert page.evaluate("() => getComputedStyle(document.documentElement).overflow") == (
            "hidden"
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


# ---------- Menu : entrées atteignables, focus, entrée courante ----------

# (largeur, hauteur, échelle) : écrans peu hauts, et 1 920 × 1 080 zoomé à 200 % (960 × 540).
SHORT_SCREENS = [(1366, 650, 1), (1280, 600, 1), (960, 540, 2)]


def menu_state(page) -> dict:
    return page.evaluate(
        """() => {
          const side = document.getElementById('side');
          return {
            scrollbar: getComputedStyle(side).scrollbarWidth,
            overflowX: document.documentElement.scrollWidth > innerWidth + 1,
          };
        }"""
    )


def open_menu_if_drawer(page):
    if page.viewport_size["width"] < 1024:
        page.locator("[data-nav-toggle]").click()
        expect(page.locator("#side")).to_be_visible()


@pytest.mark.parametrize("profile", PROFILES)
def test_every_menu_entry_is_reachable_on_short_and_zoomed_screens(
    browser, urls, company_a, profile
):
    login = browser.new_context(locale="fr-FR")
    page = login.new_page()
    sign_in(page, urls, getattr(company_a, profile))
    state = login.storage_state()
    login.close()
    problems = []
    for width, height, scale in SHORT_SCREENS:
        states = NAV_STATES if width >= 1024 else NAV_STATES[:1]
        for nav in states:
            context = browser.new_context(
                storage_state=state,
                viewport={"width": width, "height": height},
                device_scale_factor=scale,
                locale="fr-FR",
            )
            if nav == "collapsed":
                context.add_init_script("localStorage.setItem('dianna.nav', 'collapsed')")
            view = context.new_page()
            view.goto(urls("/interventions/nouveau/"))
            open_menu_if_drawer(view)
            entries = view.locator("#side .nav-item")
            for index in range(entries.count()):
                entry = entries.nth(index)
                # Clic d'essai : l'entrée défile dans le menu, est visible et reçoit le clic.
                entry.click(trial=True, timeout=3000)
            found = menu_state(view)
            label = f"{width}×{height} ×{scale} {nav}"
            if found["scrollbar"] != "none":
                problems.append(f"{label} : barre de défilement dans le menu")
            if found["overflowX"]:
                problems.append(f"{label} : débordement horizontal de la page")
            context.close()
    assert problems == [], "\n".join(problems)


def test_keyboard_focus_scrolls_the_menu_and_the_current_entry_is_visible(browser, urls, company_a):
    context = browser.new_context(viewport={"width": 1280, "height": 600}, locale="fr-FR")
    page = context.new_page()
    sign_in(page, urls, company_a.admin)
    # L'entrée courante (la dernière du menu) est visible à l'ouverture de la page.
    page.goto(urls("/administration/"))
    current = page.locator("#side [aria-current=page]")
    expect(current).to_be_in_viewport(ratio=1)
    assert page.evaluate(
        "() => { const s = document.getElementById('side'); return s.scrollTop > 0"
        " && s.classList.contains('fade-top'); }"
    )
    # Le focus clavier fait défiler le menu jusqu'à l'entrée.
    page.goto(urls("/"))
    entries = page.locator("#side a.nav-item")
    entries.first.focus()
    for _ in range(entries.count() - 1):
        page.keyboard.press("Tab")
    expect(entries.last).to_be_focused()
    expect(entries.last).to_be_in_viewport(ratio=1)
    context.close()


def test_scroll_position_is_restored_after_back(browser, urls, company_a):
    context = browser.new_context(viewport={"width": 1280, "height": 600}, locale="fr-FR")
    page = context.new_page()
    sign_in(page, urls, company_a.employee)
    page.goto(urls("/interventions/nouveau/"))
    page.mouse.wheel(0, 700)
    page.wait_for_function("() => scrollY >= 600")
    position = page.evaluate("() => scrollY")
    page.locator("#side a.nav-item", has_text="Annuaire").click()
    expect(page).to_have_url(re.compile("/annuaire/"))
    page.go_back()
    expect(page).to_have_url(re.compile("/interventions/nouveau/"))
    page.wait_for_function(f"() => Math.abs(scrollY - {position}) <= 2")
    context.close()


# ---------- Fin du menu et espacement ----------

MENU_SCREENS = [(1920, 880), (1366, 650), (1280, 600), (1440, 900), (390, 844)]
# Espacement du prototype entre deux entrées d'un même groupe : 40 px d'entrée + 2 px d'écart.
ENTRY_STEP = 42

MENU_END = """() => new Promise((done) => {
  const side = document.getElementById('side');
  side.scrollTop = side.scrollHeight;
  requestAnimationFrame(() => requestAnimationFrame(() => {
    const box = side.getBoundingClientRect();
    const fade = parseFloat(getComputedStyle(side).getPropertyValue('--side-fade'));
    const items = [...side.querySelectorAll('.nav-item')];
    const shown = [...side.children].filter((e) => getComputedStyle(e).display !== 'none');
    const last = shown[shown.length - 1].getBoundingClientRect();
    const lastItem = items[items.length - 1].getBoundingClientRect();
    const steps = [];
    for (const list of side.querySelectorAll('ul.nav')) {
      const entries = [...list.querySelectorAll('.nav-item')]
        .map((e) => e.getBoundingClientRect().top);
      for (let i = 1; i < entries.length; i++) steps.push(Math.round(entries[i] - entries[i - 1]));
    }
    done({
      inner: innerHeight, sideTop: box.top, sideBottom: box.bottom,
      topbar: document.querySelector('.topbar').getBoundingClientRect().height,
      lastBottom: last.bottom, lastItemBottom: lastItem.bottom,
      fadeBottom: side.classList.contains('fade-bottom'), fade, steps,
    });
  }));
})"""


@pytest.mark.parametrize("profile", PROFILES)
def test_the_end_of_the_menu_is_fully_visible_with_the_same_spacing(
    browser, urls, company_a, profile
):
    login = browser.new_context(locale="fr-FR")
    page = login.new_page()
    sign_in(page, urls, getattr(company_a, profile))
    state = login.storage_state()
    login.close()
    problems = []
    for width, height in MENU_SCREENS:
        modes = ["drawer"] if width < 1024 else NAV_STATES
        for mode in modes:
            context = browser.new_context(
                storage_state=state, viewport={"width": width, "height": height}, locale="fr-FR"
            )
            if mode == "collapsed":
                context.add_init_script("localStorage.setItem('dianna.nav', 'collapsed')")
            view = context.new_page()
            view.goto(urls("/"))
            open_menu_if_drawer(view)
            end = view.evaluate(MENU_END)
            label = f"{width}×{height} {mode}"
            if end["sideBottom"] > end["inner"] + 0.5:
                problems.append(f"{label} : menu jusqu'à {end['sideBottom']} px, sous l'écran")
            if (
                mode != "drawer"
                and abs(end["sideBottom"] - end["sideTop"] - (height - end["topbar"])) > 0.5
            ):
                problems.append(f"{label} : hauteur du menu différente de l'écran moins l'en-tête")
            visible_bottom = end["sideBottom"] - (end["fade"] if end["fadeBottom"] else 0)
            for name in ("lastBottom", "lastItemBottom"):
                if end[name] > visible_bottom + 0.5:
                    problems.append(f"{label} : fin du menu ({name}) cachée à {end[name]} px")
            if set(end["steps"]) != {ENTRY_STEP}:
                problems.append(f"{label} : espacements {sorted(set(end['steps']))}")
            context.close()
    assert problems == [], "\n".join(problems)
