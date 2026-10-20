"""Parcours de bout en bout (Playwright, Chromium). Lancer avec `make e2e`."""

import os
import re

import pytest

# L'API synchrone de Playwright tourne dans une boucle asyncio : Django doit l'accepter
# pour les accès à la base faits par les fixtures.
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")

# Messages de console attendus : réponses 422 (validation) et 500 (démonstration).
EXPECTED_CONSOLE = re.compile(r"status of (422|500|409)")


def pytest_collection_modifyitems(items):
    for item in items:
        if "tests/e2e" in str(item.fspath):
            item.add_marker(pytest.mark.e2e)


@pytest.fixture(autouse=True)
def site_port(request, settings):
    """Les e-mails construisent leurs liens dans la tâche, sans la requête (A3-04) : le port
    vient de SITE_PORT, ici celui du serveur de test."""
    if "live_server" in request.fixturenames:
        live_server = request.getfixturevalue("live_server")
        settings.SITE_PORT = live_server.url.rsplit(":", 1)[1]


@pytest.fixture
def styleguide_url(live_server, settings):
    settings.DEBUG = True
    return f"{live_server.url}/dev/styleguide/"


@pytest.fixture
def browser_context_args(browser_context_args):
    return {**browser_context_args, "locale": "fr-FR", "timezone_id": "Europe/Paris"}


@pytest.fixture
def console_errors(page):
    """Erreurs de console inattendues, dont les violations de CSP."""
    errors = []
    page.on(
        "console",
        lambda msg: (
            errors.append(msg.text)
            if msg.type == "error" and not EXPECTED_CONSOLE.search(msg.text)
            else None
        ),
    )
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    return errors
