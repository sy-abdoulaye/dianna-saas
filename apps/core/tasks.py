"""Tâches en arrière-plan (T-11, L3-01) : moteur base de données de django.tasks.

Le travailleur est `python manage.py db_worker` (même image que le serveur web). Les
arguments d'une tâche sont stockés en base : pas de donnée sensible au-delà de ce que
l'e-mail contient déjà."""

from django.core.mail import EmailMultiAlternatives
from django.tasks import task
from django.utils import timezone


@task
def deliver_email(
    subject: str,
    body: str,
    to: list,
    *,
    from_email: str | None = None,
    html: str = "",
    company_id: int | None = None,
    notification_id: int | None = None,
) -> str:
    """Envoie un e-mail. S'il accompagne une notification, la notification doit encore
    exister au moment de l'envoi : une action annulée (« Annuler » dans la notification
    visuelle) supprime sa notification, et l'e-mail ne part pas (L0-03)."""
    if notification_id is not None:
        from apps.core.models import Company, Notification
        from apps.core.tenancy import tenant_context

        company = Company.objects.filter(pk=company_id).first()
        if company is None:
            return "skipped"
        with tenant_context(company):
            notification = Notification.objects.filter(pk=notification_id).first()
            if notification is None or notification.email_sent_at is not None:
                return "skipped"
            _send(subject, body, to, from_email, html)
            notification.email_sent_at = timezone.now()
            notification.save(update_fields=["email_sent_at", "updated_at"])
            return "sent"
    _send(subject, body, to, from_email, html)
    return "sent"


def _send(subject, body, to, from_email, html):
    message = EmailMultiAlternatives(subject, body, from_email, to)
    if html:
        message.attach_alternative(html, "text/html")
    message.send()
