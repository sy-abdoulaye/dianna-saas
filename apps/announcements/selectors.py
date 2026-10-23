"""Lectures des annonces : liste filtrée avec l'état « lue », non lues, suivi de lecture."""

from django.db.models import Exists, OuterRef, Q, QuerySet

from apps.announcements.models import Announcement, AnnouncementRead
from apps.announcements.services import audience


def visible() -> QuerySet:
    """Annonces publiées et non supprimées."""
    return Announcement.objects.filter(deleted_at__isnull=True)


def with_read_state(queryset: QuerySet, viewer) -> QuerySet:
    return queryset.annotate(
        is_read=Exists(
            AnnouncementRead.objects.filter(announcement=OuterRef("pk"), employee=viewer)
        )
    )


def announcement_list(viewer, *, q: str = "", category: str = "") -> QuerySet:
    """Épinglées en premier, puis par date ; recherche dans le titre et le message."""
    rows = visible().select_related("author")
    if q:
        rows = rows.filter(Q(title__icontains=q) | Q(body__icontains=q))
    if category in Announcement.Category.values:
        rows = rows.filter(category=category)
    return with_read_state(rows, viewer)


def unread_count(viewer) -> int:
    return with_read_state(visible(), viewer).filter(is_read=False).count()


def latest(viewer, size: int = 3) -> list[Announcement]:
    return list(with_read_state(visible(), viewer)[:size])


def read_stats(announcement: Announcement) -> tuple[int, int]:
    """(lecteurs, salariés présents) : seules les personnes présentes sont comptées."""
    people = audience()
    readers = people.filter(
        pk__in=AnnouncementRead.objects.filter(announcement=announcement).values("employee_id")
    ).count()
    return readers, people.count()
