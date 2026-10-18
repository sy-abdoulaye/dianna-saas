"""Notifications internes (cloche). Créées par les services ; l'envoi des e-mails (M-16)
arrive au lot 3 avec les tâches en arrière-plan."""

from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme

from apps.core.models import Notification

BELL_SIZE = 8


def notify(recipient, text: str, url: str = "", kind: str = Notification.Kind.INFO):
    if url and (not url.startswith("/") or url.startswith("//")):
        raise ValueError("Le lien d'une notification doit être un chemin interne.")
    return Notification.objects.create(recipient=recipient, text=text[:255], url=url, kind=kind)


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
