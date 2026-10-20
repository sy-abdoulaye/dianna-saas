"""E-mails par le vrai travailleur de tâches (L3-01) : délai, annulation, et aucune donnée
sensible en clair dans les lignes de tâches (A3-04)."""

import json
from datetime import timedelta

import pytest
from cryptography.fernet import Fernet
from django.core import mail
from django.core.management import call_command
from django.tasks import TaskResultStatus
from django.utils import timezone
from django_tasks_db.models import DBTaskResult

from apps.accounts import services as accounts
from apps.approvals import workflow
from apps.core.mail import queue_encrypted_email, queue_notification_email
from apps.core.models import Notification
from apps.core.tenancy import tenant_context
from tests.factories import EmployeeFactory

pytestmark = pytest.mark.django_db


def _rows_text() -> str:
    return " ".join(
        json.dumps(row.args_kwargs, ensure_ascii=False)
        + json.dumps(row.return_value)
        + (row.exception_class_path or "")
        + (row.traceback or "")
        for row in DBTaskResult.objects.all()
    )


def _with_email(notification, subject="Demande validée"):
    Notification.all_companies.filter(pk=notification.pk).update(email_subject=subject)
    notification.email_subject = subject
    return notification


def test_encrypted_email_is_sent_by_the_worker(run_tasks):
    queue_encrypted_email("Sujet", "Corps secret", ["a@exemple.fr"])
    assert mail.outbox == []
    row = DBTaskResult.objects.get()
    assert "Corps secret" not in json.dumps(row.args_kwargs)
    assert "a@exemple.fr" not in json.dumps(row.args_kwargs)
    run_tasks()
    assert [(m.to, m.body) for m in mail.outbox] == [(["a@exemple.fr"], "Corps secret")]


def test_successful_results_are_deleted_right_after_sending(run_tasks):
    queue_encrypted_email("Sujet", "Corps", ["a@exemple.fr"])
    run_tasks()
    assert len(mail.outbox) == 1
    assert not DBTaskResult.objects.exists()


def test_undoable_email_waits_45_seconds(company_a, run_tasks):
    notification = _with_email(company_a.notification)
    with tenant_context(company_a.company):
        queue_notification_email(notification)
    run_tasks()
    assert mail.outbox == []
    run_tasks(after_seconds=46)
    assert len(mail.outbox) == 1
    assert mail.outbox[0].subject == "Demande validée"
    assert notification.text in mail.outbox[0].body
    assert Notification.all_companies.get(pk=notification.pk).email_sent_at


def test_undone_action_sends_nothing(company_a, run_tasks):
    notification = _with_email(company_a.notification)
    with tenant_context(company_a.company):
        queue_notification_email(notification)
        Notification.objects.filter(pk=notification.pk).delete()  # « Annuler »
    run_tasks(after_seconds=46)
    assert mail.outbox == []


def test_no_sensitive_data_left_in_task_rows(company_a, anonymous_client, submit, run_tasks):
    """Invitation, mot de passe oublié et refus : ni le lien, ni le corps, ni le motif ne
    restent en clair dans une ligne de tâche, avant comme après l'envoi."""
    reason = "Motif très personnel : rendez-vous médical"
    with tenant_context(company_a.company):
        newcomer = EmployeeFactory(company=company_a.company, user=None)
        accounts.invite(newcomer, sent_by=company_a.admin)
    anonymous_client(company_a.company).post(
        "/connexion/mot-de-passe/", {"email": company_a.employee.email}
    )
    result = submit(company_a, company_a.employee)
    with tenant_context(company_a.company):
        workflow.refuse(result.request, company_a.manager, reason=reason)

    def assert_clean():
        text = _rows_text()
        for message in mail.outbox:
            for line in message.body.splitlines():
                if "http" in line:
                    assert line.split()[-1] not in text
        assert reason not in text
        assert "/connexion/mot-de-passe/cle/" not in text
        assert "/invitation/" not in text

    assert_clean()
    run_tasks(after_seconds=46)
    bodies = " ".join(m.body for m in mail.outbox)
    assert "/invitation/" in bodies and "/connexion/mot-de-passe/cle/" in bodies
    assert reason in bodies
    assert_clean()
    assert not DBTaskResult.objects.exists()


def test_failures_are_purged_after_7_days(run_tasks, settings):
    queue_encrypted_email("Sujet", "Corps", ["a@exemple.fr"])
    settings.TASKS_ENCRYPTION_KEY = Fernet.generate_key().decode()  # clé changée : échec
    run_tasks()
    failed = DBTaskResult.objects.get()
    assert failed.status == TaskResultStatus.FAILED
    assert mail.outbox == []
    call_command("purge_task_results", verbosity=0)
    assert DBTaskResult.objects.filter(pk=failed.pk).exists()  # moins de 7 jours : gardé
    DBTaskResult.objects.filter(pk=failed.pk).update(finished_at=timezone.now() - timedelta(days=8))
    call_command("purge_task_results", verbosity=0)
    assert not DBTaskResult.objects.exists()


def test_purge_is_scheduled_in_docker_compose():
    from pathlib import Path

    from django.conf import settings

    compose = (Path(settings.BASE_DIR) / "docker-compose.yml").read_text()
    scheduler = compose.split("  scheduler:", 1)[1]
    assert "python manage.py purge_task_results" in scheduler
    assert "sleep 86400" in scheduler
