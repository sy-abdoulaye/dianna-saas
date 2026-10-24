"""Notifications internes (cloche). Créées par les services ; avec `email_subject`, un
e-mail part 45 s plus tard (M-16, L0-03), construit au moment de l'envoi (A3-04)."""

from collections.abc import Callable

from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme

from apps.core.models import Notification

BELL_SIZE = 8

# Type d'objet source → « l'objet est-il toujours d'actualité ? » (identifiant → booléen).
# La tâche d'envoi d'un e-mail le vérifie juste avant l'envoi (L6-18).
SOURCE_CHECKS: dict[str, Callable[[int], bool]] = {}


def register_source(source_type: str, is_current: Callable[[int], bool]) -> None:
    SOURCE_CHECKS[source_type] = is_current


def source_type_of(source) -> str:
    """Demande : son type (telework…) ; autre objet (annonce) : le nom de son modèle."""
    return getattr(source, "request_type", "") or source._meta.model_name


def source_is_current(notification) -> bool:
    """Faux si l'objet source a disparu (supprimé, annonce retirée) : l'e-mail ne part pas."""
    check = SOURCE_CHECKS.get(notification.source_type)
    if not notification.source_type or check is None or notification.source_id is None:
        return True
    return check(notification.source_id)


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
        source_type=source_type_of(source) if source is not None else "",
        source_id=source.pk if source is not None else None,
    )
    if email_subject and recipient.user_id and recipient.user.is_active:
        from apps.core.mail import queue_notification_email

        queue_notification_email(notification)
    return notification


def notify_many(
    recipients,
    text: str,
    url: str = "",
    kind: str = Notification.Kind.INFO,
    *,
    email_subject: str = "",
    source=None,
) -> int:
    """Même notification pour beaucoup de personnes (annonce, questionnaire publié) : une
    seule requête d'insertion au lieu d'une par personne. Les destinataires viennent du
    gestionnaire filtré de l'entreprise courante ; l'entreprise de chacun est revérifiée,
    car bulk_create ne passe pas par TenantModel.save() (règle 1). Renvoie le nombre créé."""
    from apps.core.tenancy import get_current_company

    if url and (not url.startswith("/") or url.startswith("//")):
        raise ValueError("Le lien d'une notification doit être un chemin interne.")
    company = get_current_company()
    recipients = list(recipients)
    if any(person.company_id != company.pk for person in recipients):
        raise ValueError("Destinataire d'une autre entreprise.")
    created = Notification.objects.bulk_create(
        [
            Notification(
                company=company,
                recipient=person,
                text=text[:255],
                url=url,
                kind=kind,
                email_subject=email_subject[:150],
                source_type=source_type_of(source) if source is not None else "",
                source_id=source.pk if source is not None else None,
            )
            for person in recipients
        ]
    )
    if email_subject:
        from apps.core.mail import queue_notification_email

        by_pk = {person.pk: person for person in recipients}
        for notification in created:
            person = by_pk[notification.recipient_id]
            if person.user_id and person.user.is_active:
                queue_notification_email(notification)
    return len(created)


def retract_unsent(source, *, exclude=()) -> int:
    """Supprime les notifications de `source` dont l'e-mail n'est pas encore parti : elles ne
    sont plus vraies après une nouvelle transition (A3-05). Les autres restent (historique)."""
    return (
        Notification.objects.filter(
            source_type=source_type_of(source), source_id=source.pk, email_sent_at__isnull=True
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
