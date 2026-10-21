"""Vitrine en variante discrète (L1-12) et adresse IP réelle du client."""

import pytest
from django.core import mail
from django.core.cache import cache
from django.test import Client, RequestFactory

from apps.core.http import client_ip

pytestmark = pytest.mark.django_db
SAME_MESSAGE = (
    "Si cette adresse correspond à un compte Dianna, vous allez recevoir un lien de connexion "
    "par e-mail."
)


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()
    yield
    cache.clear()


def post(email, **headers):
    return Client(HTTP_HOST="localhost").post("/", {"email": email}, **headers)


def test_same_answer_for_known_and_unknown_addresses(company_a):
    known = post(company_a.employee.email.upper())
    unknown = post("inconnu@ailleurs.fr")
    assert known.status_code == unknown.status_code == 200
    assert SAME_MESSAGE in known.content.decode().replace("&#x27;", "'")
    assert SAME_MESSAGE in unknown.content.decode().replace("&#x27;", "'")
    assert "exemple" not in known.content.decode().lower().split("<body")[1]


def test_link_is_sent_by_email_only_for_a_known_account(company_a, run_tasks):
    post("inconnu@ailleurs.fr")
    run_tasks()
    assert mail.outbox == []
    post(company_a.employee.email)
    run_tasks()
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == [company_a.employee.user.email]
    assert "http://exemple.localhost/connexion/" in mail.outbox[0].body


def test_no_link_for_accounts_without_access(company_a):
    from apps.people.models import Employee

    Employee.all_companies.filter(pk=company_a.employee.pk).update(status="left")
    post(company_a.employee.email)
    assert mail.outbox == []


def test_no_csp_exception_on_the_public_page(db):
    header = Client(HTTP_HOST="localhost").get("/").headers["Content-Security-Policy"]
    assert "form-action 'self';" in header + ";"
    assert "*.localhost" not in header


def test_limit_per_typed_address(company_a, run_tasks):
    for index in range(3):
        post(company_a.employee.email, REMOTE_ADDR=f"10.0.0.{index}")
    blocked = post(company_a.employee.email, REMOTE_ADDR="10.0.0.9")
    assert blocked.status_code == 422
    assert "Trop de tentatives" in blocked.content.decode()
    run_tasks()
    assert len(mail.outbox) == 3


def test_limit_per_real_client_ip_behind_trusted_proxy(company_a, settings):
    settings.TRUSTED_PROXY_COUNT = 1
    for index in range(10):
        # L'attaquant change la partie gauche de X-Forwarded-For : elle n'est pas crue.
        post(f"a{index}@ailleurs.fr", HTTP_X_FORWARDED_FOR=f"1.1.1.{index}, 203.0.113.7")
    blocked = post("autre@ailleurs.fr", HTTP_X_FORWARDED_FOR="9.9.9.9, 203.0.113.7")
    assert blocked.status_code == 422
    other_client = post("autre@ailleurs.fr", HTTP_X_FORWARDED_FOR="9.9.9.9, 198.51.100.4")
    assert other_client.status_code == 200


def test_typed_address_and_ip_are_not_stored_in_clear(company_a):
    """Compteurs en base (L1-16) : seules des empreintes HMAC sont enregistrées."""
    from apps.core import ratelimit
    from apps.core.forms import email_digest
    from apps.core.models import RateLimitCounter

    post(company_a.employee.email)
    key = f"space-access:email:{email_digest(company_a.employee.email)}"
    assert ratelimit.current(key, 10 * 60) == 1
    stored = list(RateLimitCounter.objects.values_list("key", flat=True))
    assert len(stored) == 2  # adresse IP et adresse saisie
    assert all(len(k) == 64 and "@" not in k and "." not in k for k in stored)


@pytest.mark.parametrize(
    ("count", "forwarded", "remote", "expected"),
    [
        (0, "1.2.3.4", "10.0.0.1", "10.0.0.1"),
        (1, "6.6.6.6, 1.2.3.4", "10.0.0.1", "1.2.3.4"),
        (2, "6.6.6.6, 1.2.3.4, 10.0.0.2", "10.0.0.1", "1.2.3.4"),
        (2, "1.2.3.4", "10.0.0.1", "10.0.0.1"),
        (1, "pas-une-ip", "10.0.0.1", "10.0.0.1"),
    ],
)
def test_client_ip(settings, count, forwarded, remote, expected):
    settings.TRUSTED_PROXY_COUNT = count
    request = RequestFactory().get("/", HTTP_X_FORWARDED_FOR=forwarded, REMOTE_ADDR=remote)
    assert client_ip(request) == expected
