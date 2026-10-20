"""File d'envoi des e-mails : toujours par une tâche.

Le moteur base de données enregistre la tâche dans la transaction en cours : si l'action
échoue et que la transaction est annulée, la tâche disparaît avec elle ; sinon le
travailleur la voit à la validation.

- Invitations et e-mails d'allauth : sans délai (L1-14, L3-11).
- E-mails liés à une action annulable : 45 s (UNDOABLE_EMAIL_DELAY_SECONDS, L0-03) ; ils ne
  partent pas si l'action a été annulée entre-temps (la notification n'existe plus)."""

from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from apps.core.tasks import deliver_email


def queue_email(
    subject: str,
    body: str,
    to: list,
    *,
    from_email=None,
    html: str = "",
    notification=None,
    delay_seconds: int = 0,
) -> None:
    kwargs = {"from_email": from_email, "html": html}
    if notification is not None:
        kwargs.update(company_id=notification.company_id, notification_id=notification.pk)

    task = deliver_email
    if delay_seconds:
        task = task.using(run_after=timezone.now() + timedelta(seconds=delay_seconds))
    task.enqueue(subject, body, list(to), **kwargs)


def queue_undoable_email(subject: str, body: str, to: list, *, notification) -> None:
    queue_email(
        subject,
        body,
        to,
        notification=notification,
        delay_seconds=settings.UNDOABLE_EMAIL_DELAY_SECONDS,
    )
