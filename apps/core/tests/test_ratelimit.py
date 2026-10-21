"""Limite de fréquence comptée en base (L4-17, L1-16) : atomique, persistante, purgée."""

import threading
from datetime import timedelta

import pytest
from django.core.management import call_command
from django.db import connection
from django.test import Client
from django.utils import timezone

from apps.core import ratelimit
from apps.core.models import RateLimitCounter
from apps.people.models import Employee


@pytest.mark.django_db(transaction=True)
def test_30_simultaneous_exports_give_10_accepted_and_20_refused(company_a, client_for):
    hr = Employee.all_companies.get(pk=company_a.hr.pk)
    signed_in = client_for(hr)
    url = "/planning/export/fichier/?periode=semaine&format=csv"
    barrier = threading.Barrier(30)
    statuses = []

    def export():
        client = Client(HTTP_HOST=signed_in.defaults["HTTP_HOST"])
        client.cookies = signed_in.cookies
        try:
            barrier.wait()
            statuses.append(client.get(url).status_code)
        finally:
            connection.close()

    threads = [threading.Thread(target=export) for _ in range(30)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(statuses) == [200] * 10 + [429] * 20
    assert RateLimitCounter.objects.get().count == 30


@pytest.mark.django_db
def test_other_keys_never_erase_a_counter():
    for _n in range(5):
        ratelimit.hit("exports:1:42", 600)
    for n in range(400):
        ratelimit.hit(f"autre-cle:{n}", 600)
    assert ratelimit.current("exports:1:42", 600) == 5
    assert RateLimitCounter.objects.count() == 401


@pytest.mark.django_db
def test_a_new_window_starts_from_zero(monkeypatch):
    for _n in range(3):
        ratelimit.hit("cle", 600)
    later = timezone.now() + timedelta(seconds=601)
    monkeypatch.setattr(timezone, "now", lambda: later)
    assert ratelimit.current("cle", 600) == 0
    assert ratelimit.hit("cle", 600) == 1


@pytest.mark.django_db
def test_expired_windows_are_purged_by_the_scheduled_purge():
    ratelimit.hit("ancienne", 600)
    RateLimitCounter.objects.update(window_start=timezone.now() - timedelta(days=2))
    ratelimit.hit("courante", 600)
    call_command("purge_task_results", verbosity=0)
    assert list(RateLimitCounter.objects.values_list("count", flat=True)) == [1]
    assert ratelimit.current("courante", 600) == 1


@pytest.mark.django_db
def test_keys_are_hmac_digests():
    ratelimit.hit("space-access:ip:203.0.113.7", 600)
    stored = RateLimitCounter.objects.get().key
    assert "203.0.113.7" not in stored and len(stored) == 64
