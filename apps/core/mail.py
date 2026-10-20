"""Mise en file des e-mails : toujours par une tâche (L3-01), jamais de contenu sensible en
clair dans la ligne de tâche (A3-04, voir apps/core/tasks.py).

Le moteur base de données enregistre la tâche dans la transaction en cours : si l'action
échoue, la tâche disparaît avec elle."""

import json
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from apps.core import crypto, tasks


def _later(task, delay_seconds: int):
    if delay_seconds:
        return task.using(run_after=timezone.now() + timedelta(seconds=delay_seconds))
    return task


def queue_notification_email(notification, *, delay_seconds: int | None = None) -> None:
    """E-mail d'une notification, 45 s après l'action par défaut (annulable, L0-03)."""
    if delay_seconds is None:
        delay_seconds = settings.UNDOABLE_EMAIL_DELAY_SECONDS
    _later(tasks.send_notification_email, delay_seconds).enqueue(
        notification.company_id, notification.pk
    )


def queue_invitation_email(invitation) -> None:
    tasks.send_invitation_email.enqueue(invitation.company_id, invitation.pk)


def queue_space_link_email(employee) -> None:
    tasks.send_space_link_email.enqueue(employee.company_id, employee.pk)


def queue_encrypted_email(
    subject: str, body: str, to: list, *, from_email=None, html: str = ""
) -> None:
    """E-mail déjà rendu (allauth) : contenu chiffré dans la ligne de tâche."""
    payload = json.dumps(
        {"subject": subject, "body": body, "to": list(to), "from_email": from_email, "html": html}
    )
    tasks.send_encrypted_email.enqueue(crypto.encrypt("TASKS_ENCRYPTION_KEY", payload))
