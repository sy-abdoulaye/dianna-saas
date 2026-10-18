import json

import pytest
from django.urls import reverse

pytestmark = pytest.mark.django_db


@pytest.fixture
def debug(settings):
    settings.DEBUG = True


def assert_csp(response):
    header = response.headers["Content-Security-Policy"]
    assert "default-src 'self'" in header
    assert "unsafe-inline" not in header


@pytest.mark.parametrize(
    ("slug", "title"),
    [
        ("403", "Accès non autorisé"),
        ("404", "Page introuvable"),
        ("500", "Erreur du serveur"),
        ("module-desactive", "Module désactivé"),
    ],
)
def test_error_pages_render_with_the_design(client, debug, slug, title):
    response = client.get(reverse("dev:page", args=[slug]))
    assert response.status_code == 200
    content = response.content.decode()
    assert title in content
    assert "Retour au tableau de bord" in content
    assert_csp(response)


def test_404_handler_uses_the_design_page(client):
    response = client.get("/cette-page-n-existe-pas/")
    assert response.status_code == 404
    assert "Page introuvable" in response.content.decode()
    assert_csp(response)


def test_styleguide_is_hidden_when_debug_is_off(client, settings):
    settings.DEBUG = False
    assert client.get(reverse("dev:styleguide")).status_code == 404
    assert client.get(reverse("dev:modal")).status_code == 404


def test_styleguide_renders_every_component_section(client, debug):
    response = client.get(reverse("dev:styleguide"))
    assert response.status_code == 200
    content = response.content.decode()
    for marker in [
        'class="skip-link"',
        'id="content"',
        'id="modal-root"',
        'id="tpl-toast"',
        'id="tpl-server-error"',
        "data-theme-switch",
        "Télétravail",
        "Bientôt",
        "1 à 8 sur 24",
        'class="stepper"',
        "<progress",
        "<meter",
        "data-dropzone",
    ]:
        assert marker in content, marker
    assert content.count("<h1") == 1
    assert_csp(response)
    nonce = response.headers["Content-Security-Policy"].split("'nonce-")[1].split("'")[0]
    assert f'nonce="{nonce}"' in content


def test_styleguide_filters_return_only_the_results_fragment(client, debug):
    response = client.get(
        reverse("dev:styleguide") + "?q=zzzz",
        headers={"HX-Request": "true", "HX-Target": "results"},
    )
    content = response.content.decode()
    assert "Aucun collaborateur trouvé" in content
    assert "<html" not in content


def test_styleguide_filters_work_without_javascript(client, debug):
    response = client.get(reverse("dev:styleguide") + "?service=Finance")
    content = response.content.decode()
    assert "1 à 4 sur 4" in content
    assert "<html" in content


def test_modal_form_returns_422_with_errors(client, debug):
    response = client.post(reverse("dev:modal"), {"day": "2026-10-24"})  # un samedi
    assert response.status_code == 422
    content = response.content.decode()
    assert "Le télétravail se déclare du lundi au vendredi." in content
    assert "1 information est à corriger." in content
    assert 'value="2026-10-24"' in content  # la saisie est conservée
    assert "<dialog" not in content  # seul le formulaire est renvoyé


def test_modal_form_success_triggers_toast_with_undo(client, debug):
    response = client.post(reverse("dev:modal"), {"day": "2026-10-22"})
    assert response.status_code == 204
    payload = json.loads(response.headers["HX-Trigger"])
    assert payload["closeModal"] is True
    assert payload["toast"]["title"] == "Demande envoyée"
    undo_response = client.post(payload["toast"]["undo_url"])
    assert undo_response.status_code == 204
    assert json.loads(undo_response.headers["HX-Trigger"])["toast"]["title"] == "Action annulée"


def test_undo_after_the_window_shows_the_error_toast(client, debug, settings):
    response = client.post(reverse("dev:modal"), {"day": "2026-10-22"})
    url = json.loads(response.headers["HX-Trigger"])["toast"]["undo_url"]
    settings.UNDO_WINDOW_SECONDS = -1
    undo_response = client.post(url)
    assert undo_response.status_code == 409
    toast = json.loads(undo_response.headers["HX-Trigger"])["toast"]
    assert toast == {"title": "Il est trop tard pour annuler cette action.", "kind": "err"}


def test_confirm_modal_variants(client, debug):
    danger = client.get(reverse("dev:confirm") + "?danger=1").content.decode()
    assert "is-danger" in danger and "btn-danger" in danger
    normal = client.get(reverse("dev:confirm")).content.decode()
    assert "is-ok" in normal and "btn-primary" in normal


def test_demo_server_error_returns_500(client, debug):
    assert client.post(reverse("dev:server_error")).status_code == 500
