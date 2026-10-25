"""Changements d'état des annonces : publier, modifier, épingler, supprimer et rétablir,
marquer comme lue. Chaque action est inscrite au journal, sans le contenu de l'annonce."""

from dataclasses import asdict, dataclass

from django.db import IntegrityError, transaction
from django.db.models import QuerySet
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.announcements.models import BODY_MAX, BODY_MIN, TITLE_MAX, Announcement, AnnouncementRead
from apps.core import audit, notifications, permissions
from apps.core.context import ActionContext
from apps.core.errors import ServiceError
from apps.core.models import Notification
from apps.people.models import Employee, EmployeeStatus

EDITABLE_FIELDS = ("title", "category", "body", "pinned")


@dataclass(frozen=True)
class AnnouncementData:
    """Contenu d'une annonce, publié ou modifié par les RH."""

    title: str
    category: str
    body: str
    pinned: bool = False


GONE = _("Cette annonce a été supprimée.")


class AnnouncementError(ServiceError):
    """Refus d'une action sur une annonce (message affiché, champ éventuel)."""


def audience() -> QuerySet[Employee]:
    """Personnes visées par une annonce : tous les salariés présents (statut « Actif »)."""
    return Employee.objects.filter(status=EmployeeStatus.ACTIVE)


def can_see_reads(viewer: Employee, announcement: Announcement) -> bool:
    """Suivi de lecture (« Lectures : x sur y ») : l'auteur, les RH et l'administrateur
    seulement. Seule fonction qui en décide (vue et gabarit)."""
    return announcement.author_id == viewer.pk or permissions.can(viewer, "announcements.manage")


def _check(data: AnnouncementData) -> None:
    """Contrôles du service (A3-02), refaits même si le formulaire les a déjà faits."""
    if not data.title.strip() or len(data.title) > TITLE_MAX:
        raise AnnouncementError(_("Le titre est obligatoire."), "title")
    if data.category not in Announcement.Category.values:
        raise AnnouncementError(_("Choisissez une catégorie."), "category")
    body = data.body.strip()
    if not body:
        raise AnnouncementError(_("Le message est obligatoire."), "body")
    if len(body) < BODY_MIN:
        raise AnnouncementError(_("Le message est trop court (15 caractères minimum)."), "body")
    if len(body) > BODY_MAX:
        raise AnnouncementError(_("Le message dépasse 5 000 caractères."), "body")


@transaction.atomic
def publish(data: AnnouncementData, *, context: ActionContext) -> Announcement:
    """Publie l'annonce et prévient tous les salariés présents ; une annonce épinglée part
    aussi par e-mail (M-16). L'auteur l'a déjà lue."""
    actor, request = context.person(), context.request
    _check(data)
    announcement = Announcement.objects.create(
        **asdict(data),
        author=actor,
        published_at=timezone.now(),
    )
    AnnouncementRead.objects.create(announcement=announcement, employee=actor)
    _notify(announcement, audience().exclude(pk=actor.pk))
    audit.log(
        "announcements.published",
        _("Annonce publiée : %(title)s") % {"title": announcement.title},
        actor=actor,
        target=announcement,
        request=request,
    )
    return announcement


def _notify(announcement: Announcement, people: QuerySet[Employee]) -> list[Notification]:
    """Notification « Nouvelle annonce » ; e-mail 45 s plus tard si elle est épinglée."""
    text = _("Nouvelle annonce : %(title)s") % {"title": announcement.title}
    return notifications.notify_many(
        people.select_related("user"),
        text,
        url=f"/annonces/{announcement.public_id}/",
        email_subject=text if announcement.pinned else "",
        source=announcement,
    )


def _lock(announcement: Announcement) -> Announcement:
    locked = (
        Announcement.objects.select_for_update()
        .filter(pk=announcement.pk, deleted_at__isnull=True)
        .first()
    )
    if locked is None:
        raise AnnouncementError(GONE)
    return locked


@transaction.atomic
def update(
    announcement: Announcement, data: AnnouncementData, *, context: ActionContext
) -> Announcement:
    """Modifie l'annonce, sans nouvelle notification ni e-mail (L6-08)."""
    actor, request = context.actor, context.request
    _check(data)
    announcement = _lock(announcement)
    for name, value in asdict(data).items():
        setattr(announcement, name, value)
    announcement.save()
    audit.log(
        "announcements.updated",
        _("Annonce modifiée : %(title)s") % {"title": announcement.title},
        actor=actor,
        target=announcement,
        request=request,
    )
    return announcement


@transaction.atomic
def toggle_pin(announcement: Announcement, *, context: ActionContext) -> Announcement:
    """Épingler ou désépingler ; épingler plus tard n'envoie pas d'e-mail (L6-08)."""
    actor, request = context.actor, context.request
    announcement = _lock(announcement)
    announcement.pinned = not announcement.pinned
    announcement.save(update_fields=["pinned", "updated_at"])
    audit.log(
        "announcements.pinned" if announcement.pinned else "announcements.unpinned",
        (
            _("Annonce épinglée : %(title)s")
            if announcement.pinned
            else _("Annonce désépinglée : %(title)s")
        )
        % {"title": announcement.title},
        actor=actor,
        target=announcement,
        request=request,
    )
    return announcement


@transaction.atomic
def delete(announcement: Announcement, *, context: ActionContext) -> Announcement:
    """Suppression logique, annulable 30 s depuis la notification visuelle (L6-09)."""
    actor, request = context.actor, context.request
    announcement = _lock(announcement)
    announcement.deleted_at = timezone.now()
    announcement.save(update_fields=["deleted_at", "updated_at"])
    # Notifications dont l'e-mail n'est pas parti : retirées (une annonce épinglée supprimée
    # dans les 45 s n'envoie aucun e-mail, L6-18). Les autres restent, avec leur lien.
    notifications.retract_unsent(announcement)
    audit.log(
        "announcements.deleted",
        _("Annonce supprimée : %(title)s") % {"title": announcement.title},
        actor=actor,
        target=announcement,
        request=request,
    )
    return announcement


@transaction.atomic
def restore(public_id: str, *, context: ActionContext) -> Announcement:
    """« Annuler » après une suppression : l'annonce redevient visible pour tous."""
    actor, request = context.actor, context.request
    announcement = (
        Announcement.objects.select_for_update()
        .filter(public_id=public_id, deleted_at__isnull=False)
        .first()
    )
    if announcement is None:
        raise AnnouncementError(_("Cette annonce a déjà été rétablie."))
    announcement.deleted_at = None
    announcement.save(update_fields=["deleted_at", "updated_at"])
    # Notifications retirées à la suppression : recréées pour ceux qui n'en ont plus ; un
    # e-mail déjà parti n'est jamais renvoyé (sa notification n'a pas été retirée).
    notified = Notification.objects.filter(
        source_type=notifications.source_type_of(announcement), source_id=announcement.pk
    ).values("recipient_id")
    others = audience().exclude(pk=announcement.author_id).exclude(pk__in=notified)
    _notify(announcement, others)
    audit.log(
        "announcements.restored",
        _("Suppression annulée : %(title)s") % {"title": announcement.title},
        actor=actor,
        target=announcement,
        request=request,
    )
    return announcement


def mark_read(announcement: Announcement, employee: Employee) -> bool:
    """Première ouverture : une lecture pour cette seule personne. Renvoie True si elle est
    nouvelle ; deux ouvertures simultanées n'en créent qu'une (contrainte unique)."""
    if AnnouncementRead.objects.filter(announcement=announcement, employee=employee).exists():
        return False
    try:
        with transaction.atomic():
            AnnouncementRead.objects.create(announcement=announcement, employee=employee)
    except IntegrityError:
        return False
    return True
