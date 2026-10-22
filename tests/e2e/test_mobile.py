"""Largeur mobile (390 px) : aucune page ne déborde de l'écran. Les tableaux larges (planning
semaine et mois, annuaire, campagnes, utilisateurs, onglets du matériel) défilent dans leur
conteneur, jamais la page entière."""

import pytest

from tests.e2e.test_requests import sign_in

pytestmark = pytest.mark.django_db(transaction=True)

PAGES = [
    "/",
    "/planning/",
    "/planning/?vue=mois",
    "/planning/export/",
    "/annuaire/",
    "/annuaire/nouveau/",
    "/teletravail/",
    "/teletravail/?onglet=a-valider",
    "/teletravail/?onglet=equipe",
    "/conges/",
    "/conges/campagnes/",
    "/astreintes/",
    "/transport/",
    "/transport/?onglet=a-valider",
    "/materiel/",
    "/materiel/?onglet=equipe",
    "/materiel/?onglet=parc",
    "/materiel/?onglet=demandes",
    "/materiel/?onglet=signalements",
    "/notifications/",
    "/compte/securite/",
    "/administration/",
    "/administration/utilisateurs/",
    "/administration/structure/",
    "/administration/fermetures/",
    "/administration/modules/",
    "/administration/journal/",
]

OVERFLOW = """() => {
  const doc = document.documentElement;
  if (doc.scrollWidth <= doc.clientWidth) return null;
  // Diagnostic : premier élément qui dépasse sans conteneur qui défile au-dessus de lui.
  const clipped = (el) => {
    for (let p = el.parentElement; p && p !== document.body; p = p.parentElement) {
      if (getComputedStyle(p).overflowX !== "visible") return true;
    }
    return false;
  };
  const wide = [...document.querySelectorAll("body *")].find(
    (el) => el.getBoundingClientRect().right > doc.clientWidth + 1 && !clipped(el)
  );
  const name = wide ? `${wide.tagName}.${wide.className}` : "?";
  return `${doc.scrollWidth} > ${doc.clientWidth} (${name})`;
}"""


@pytest.fixture
def urls(live_server):
    port = live_server.url.rsplit(":", 1)[1]
    return lambda path="/": f"http://exemple.localhost:{port}{path}"


@pytest.mark.parametrize("profile", ["employee", "manager", "hr", "admin"])
def test_no_page_is_wider_than_a_phone_screen(browser, urls, company_a, profile):
    context = browser.new_context(
        locale="fr-FR", timezone_id="Europe/Paris", viewport={"width": 390, "height": 844}
    )
    page = context.new_page()
    sign_in(page, urls, getattr(company_a, profile))
    too_wide = {}
    for path in PAGES:
        page.goto(urls(path))
        page.wait_for_load_state("networkidle")
        if (overflow := page.evaluate(OVERFLOW)) is not None:
            too_wide[path] = overflow
    context.close()
    assert too_wide == {}
