"""Notifications internes (cloche). Créées par les services ; avec `email_subject`, un
e-mail part 45 s plus tard (M-16, L0-03), construit au moment de l'envoi (A3-04)."""

from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme

from apps.core.models import Notification

BELL_SIZE = 8


def notify(
    recipient,
    text: str,
    url: str = "",
    kind: str = Notification.Kind.INFO,
    *,
    email_subject: str = "",
    source=None,
):
    """Crée la notification. `source` (une demande…) permet de retirer plus tard les
    notifications devenues fausses ; `email_subject` met l'e-mail en file (45 s)."""
    if url and (not url.startswith("/") or url.startswith("//")):
        raise ValueError("Le lien d'une notification doit être un chemin interne.")
    notification = Notification.objects.create(
        recipient=recipient,
        text=text[:255],
        url=url,
        kind=kind,
        email_subject=email_subject[:150],
        source_type=getattr(source, "request_type", "") if source is not None else "",
        source_id=source.pk if source is not None else None,
    )
    if email_subject and recipient.user_id and recipient.user.is_active:
        from apps.core.mail import queue_notification_email

        queue_notification_email(notification)
    return notification


def retract_unsent(source, *, exclude=()) -> int:
    """Supprime les notifications de `source` dont l'e-mail n'est pas encore parti : elles ne
    sont plus vraies après une nouvelle transition (A3-05). Les autres restent (historique)."""
    return (
        Notification.objects.filter(
            source_type=source.request_type, source_id=source.pk, email_sent_at__isnull=True
        )
        .exclude(pk__in=list(exclude))
        .delete()[0]
    )


def for_employee(employee):
    return Notification.objects.filter(recipient=employee)


def unread_count(employee) -> int:
    return for_employee(employee).filter(read_at__isnull=True).count()


def latest(employee, size: int = BELL_SIZE):
    return list(for_employee(employee)[:size])


def mark_read(notification):
    if notification.read_at is None:
        notification.read_at = timezone.now()
        notification.save(update_fields=["read_at", "updated_at"])


def mark_all_read(employee) -> int:
    return (
        for_employee(employee)
        .filter(read_at__isnull=True)
        .update(read_at=timezone.now(), updated_at=timezone.now())
    )


def safe_target(notification) -> str:
    url = notification.url or "/"
    if not url_has_allowed_host_and_scheme(url, allowed_hosts=None) or not url.startswith("/"):
        return "/"
    return url
