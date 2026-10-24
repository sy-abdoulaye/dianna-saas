"""Navigation unique après une action (R1-02) : after_action et l'adresse rechargée."""

import json

import pytest
from django.test import RequestFactory

from apps.core.context_processors import page_url
from apps.core.htmx import PAGE_CHANGED, RELOAD_PAGE, Toast, after_action

TOAST = Toast(title="Enregistré")


def htmx_request(method="post", path="/action/", **headers):
    request = getattr(RequestFactory(), method)(path, **headers)
    request.htmx = True
    return request


def test_same_page_reloads_the_zone_with_a_toast():
    response = after_action(htmx_request(), TOAST, refresh=PAGE_CHANGED, close_modal=True)
    events = json.loads(response["HX-Trigger"])
    assert response.status_code == 204
    assert events["toast"]["title"] == "Enregistré"
    assert events[PAGE_CHANGED] is True and events["closeModal"] is True
    assert "HX-Location" not in response


def test_another_page_is_reached_by_hx_location():
    response = after_action(htmx_request(), TOAST, go_to="/annonces/")
    assert json.loads(response["HX-Location"])["path"] == "/annonces/"
    assert json.loads(response["HX-Trigger"])["toast"]["title"] == "Enregistré"


def test_reload_page_is_the_only_full_reload():
    response = after_action(htmx_request(), TOAST, refresh=RELOAD_PAGE)
    assert response["HX-Refresh"] == "true"


def test_refresh_and_go_to_are_exclusive():
    with pytest.raises(ValueError):
        after_action(htmx_request(), TOAST, refresh=PAGE_CHANGED, go_to="/")


@pytest.mark.django_db
def test_page_form_without_javascript_gets_a_message_and_a_redirect(client_for, company_a):
    from django.contrib.messages import get_messages
    from django.contrib.messages.storage.fallback import FallbackStorage

    request = RequestFactory().post("/x/")
    request.htmx = False
    request.session = client_for(company_a.employee).session
    request._messages = FallbackStorage(request)
    response = after_action(request, TOAST, go_to="/annuaire/", page_form=True)
    assert response.status_code == 302 and response["Location"] == "/annuaire/"
    assert [str(m) for m in get_messages(request)] == ["Enregistré"]


def test_a_page_rendered_by_a_post_reloads_the_address_shown_in_the_browser():
    get = RequestFactory().get("/questionnaires/x/?vue=resultats")
    assert page_url(get) == "/questionnaires/x/?vue=resultats"
    post = RequestFactory().post(
        "/questionnaires/x/repondre/",
        HTTP_HX_CURRENT_URL="http://testserver/questionnaires/x/?vue=resultats",
    )
    assert page_url(post) == "/questionnaires/x/?vue=resultats"
    other_host = RequestFactory().post(
        "/questionnaires/x/repondre/", HTTP_HX_CURRENT_URL="https://ailleurs.fr/piege/"
    )
    assert page_url(other_host) == "/questionnaires/x/repondre/"
