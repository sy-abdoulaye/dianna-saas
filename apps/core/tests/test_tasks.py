"""E-mails par le vrai travailleur de tâches (L3-01) : délai et annulation."""

import pytest
from django.core import mail

from apps.core.mail import queue_email, queue_undoable_email
from apps.core.models import Notification
from apps.core.tenancy import tenant_context

pytestmark = pytest.mark.django_db


def test_email_is_sent_by_the_worker(run_tasks):
    queue_email("Sujet", "Corps", ["a@exemple.fr"])
    assert mail.outbox == []
    run_tasks()
    assert [m.to for m in mail.outbox] == [["a@exemple.fr"]]


def test_undoable_email_waits_45_seconds(company_a, run_tasks):
    with tenant_context(company_a.company):
        queue_undoable_email(
            "Demande validée", "Corps", ["c@exemple.fr"], notification=company_a.notification
        )
    run_tasks()
    assert mail.outbox == []
    run_tasks(after_seconds=46)
    assert len(mail.outbox) == 1
    assert Notification.all_companies.get(pk=company_a.notification.pk).email_sent_at


def test_undone_action_sends_nothing(company_a, run_tasks):
    with tenant_context(company_a.company):
        queue_undoable_email(
            "Demande validée", "Corps", ["c@exemple.fr"], notification=company_a.notification
        )
        Notification.objects.filter(pk=company_a.notification.pk).delete()  # « Annuler »
    run_tasks(after_seconds=46)
    assert mail.outbox == []
