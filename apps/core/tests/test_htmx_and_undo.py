import json
import time

import pytest
from django.contrib.auth.models import AnonymousUser
from django.contrib.sessions.backends.db import SessionStore
from django.http import HttpResponse
from django.test import RequestFactory

from apps.core import undo
from apps.core.htmx import Toast, toast_response, trigger


def test_toast_rejects_unknown_kind():
    with pytest.raises(ValueError):
        Toast(title="X", kind="success")


def test_toast_response_sets_hx_trigger_and_closes_modal():
    response = toast_response(Toast(title="Demande envoyée", undo_url="/u/"), close_modal=True)
    assert response.status_code == 204
    payload = json.loads(response.headers["HX-Trigger"])
    assert payload["toast"] == {"title": "Demande envoyée", "kind": "ok", "undo_url": "/u/"}
    assert payload["closeModal"] is True


def test_trigger_merges_existing_events():
    response = HttpResponse()
    trigger(response, refresh=True)
    trigger(response, toast=Toast(title="A", kind="info"))
    payload = json.loads(response.headers["HX-Trigger"])
    assert payload["refresh"] is True and payload["toast"]["kind"] == "info"


@pytest.fixture
def make_request(db):
    def _make(session_key=None):
        request = RequestFactory().post("/")
        request.session = SessionStore(session_key)
        request.user = AnonymousUser()
        return request

    return _make


def test_undo_token_round_trip(make_request):
    request = make_request()
    token = undo.make_token(request, "telework.submit", "abc")
    payload = undo.read_token(request, token)
    assert payload.action == "telework.submit" and payload.target == "abc"


def test_undo_token_expires_after_the_window(make_request, monkeypatch, settings):
    settings.UNDO_WINDOW_SECONDS = 30
    request = make_request()
    token = undo.make_token(request, "a", "b")
    later = time.time() + 31
    monkeypatch.setattr("django.core.signing.time.time", lambda: later)
    with pytest.raises(undo.UndoError) as error:
        undo.read_token(request, token)
    assert str(error.value.message) == "Il est trop tard pour annuler cette action."


def test_only_the_author_can_undo(make_request):
    author = make_request()
    token = undo.make_token(author, "a", "b")
    other = make_request()
    with pytest.raises(undo.UndoError) as error:
        undo.read_token(other, token)
    assert "auteur" in str(error.value.message)


def test_tampered_token_is_refused(make_request):
    request = make_request()
    token = undo.make_token(request, "a", "b")
    with pytest.raises(undo.UndoError):
        undo.read_token(request, token[:-2] + "xx")
