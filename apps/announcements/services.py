"""Changements d'état des annonces : publier, modifier, épingler, supprimer et rétablir,
marquer comme lue. Chaque action est inscrite au journal, sans le contenu de l'annonce."""

from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.announcements.models import BODY_MAX, BODY_MIN, TITLE_MAX, Announcement, AnnouncementRead
from apps.core import audit, notifications, permissions
from apps.core.errors import ServiceError
from apps.people.models import Employee, EmployeeStatus

EDITABLE_FIELDS = ("title", "category", "body", "pinned")
GONE = _("Cette annonce a été supprimée.")


class AnnouncementError(ServiceError):
    """Refus d'une action sur une annonce (message affiché, champ éventuel)."""


def audience():
    """Personnes visées par une annonce : tous les salariés présents (statut « Actif »)."""
    return Employee.objects.filter(status=EmployeeStatus.ACTIVE)


def can_see_reads(viewer, announcement: Announcement) -> bool:
    """Suivi de lecture (« Lectures : x sur y ») : l'auteur, les RH et l'administrateur
    seulement. Seule fonction qui en décide (vue et gabarit)."""
    return announcement.author_id == viewer.pk or permissions.can(viewer, "announcements.manage")


def _check(data: dict) -> None:
    """Contrôles du service (A3-02), refaits même si le formulaire les a déjà faits."""
    if not data.get("title", "").strip() or len(data["title"]) > TITLE_MAX:
        raise AnnouncementError(_("Le titre est obligatoire."), "title")
    body = data.get("body", "").strip()
    if not body:
        raise AnnouncementError(_("Le message est obligatoire."), "body")
    if len(body) < BODY_MIN:
        raise AnnouncementError(_("Le message est trop court (15 caractères minimum)."), "body")
    if len(body) > BODY_MAX:
        raise AnnouncementError(_("Le message dépasse 5 000 caractères."), "body")


@transaction.atomic
def publish(data: dict, *, actor, request=None) -> Announcement:
    """Publie l'annonce et prévient tous les salariés présents ; une annonce épinglée part
    aussi par e-mail (M-16). L'auteur l'a déjà lue."""
    _check(data)
    announcement = Announcement.objects.create(
        **{name: data[name] for name in EDITABLE_FIELDS},
        author=actor,
        published_at=timezone.now(),
    )
    AnnouncementRead.objects.create(announcement=announcement, employee=actor)
    notifications.notify_many(
        audience().exclude(pk=actor.pk).select_related("user"),
        _("Nouvelle annonce : %(title)s") % {"title": announcement.title},
        url=f"/annonces/{announcement.public_id}/",
        email_subject=_("Nouvelle annonce : %(title)s") % {"title": announcement.title}
        if announcement.pinned
        else "",
    )
    audit.log(
        "announcements.published",
        _("Annonce publiée : %(title)s") % {"title": announcement.title},
        actor=actor,
        target=announcement,
        request=request,
    )
    return announcement


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
def update(announcement: Announcement, data: dict, *, actor, request=None) -> Announcement:
    """Modifie l'annonce, sans nouvelle notification ni e-mail (L6-08)."""
    _check(data)
    announcement = _lock(announcement)
    for name in EDITABLE_FIELDS:
        setattr(announcement, name, data[name])
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
def toggle_pin(announcement: Announcement, *, actor, request=None) -> Announcement:
    """Épingler ou désépingler ; épingler plus tard n'envoie pas d'e-mail (L6-08)."""
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
def delete(announcement: Announcement, *, actor, request=None) -> Announcement:
    """Suppression logique, annulable 30 s depuis la notification visuelle (L6-09)."""
    announcement = _lock(announcement)
    announcement.deleted_at = timezone.now()
    announcement.save(update_fields=["deleted_at", "updated_at"])
    audit.log(
        "announcements.deleted",
        _("Annonce supprimée : %(title)s") % {"title": announcement.title},
        actor=actor,
        target=announcement,
        request=request,
    )
    return announcement


@transaction.atomic
def restore(public_id: str, *, actor, request=None) -> Announcement:
    """« Annuler » après une suppression : l'annonce redevient visible pour tous."""
    announcement = (
        Announcement.objects.select_for_update()
        .filter(public_id=public_id, deleted_at__isnull=False)
        .first()
    )
    if announcement is None:
        raise AnnouncementError(_("Cette annonce a déjà été rétablie."))
    announcement.deleted_at = None
    announcement.save(update_fields=["deleted_at", "updated_at"])
    audit.log(
        "announcements.restored",
        _("Suppression annulée : %(title)s") % {"title": announcement.title},
        actor=actor,
        target=announcement,
        request=request,
    )
    return announcement


def mark_read(announcement: Announcement, employee) -> bool:
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
