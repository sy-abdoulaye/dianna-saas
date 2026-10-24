"""Communication interne (docs/modules/08-annonces.md)."""

import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import Module, TenantModel

TITLE_MAX = 120
BODY_MIN, BODY_MAX = 15, 5000


class Announcement(TenantModel):
    class Category(models.TextChoices):
        COMPANY = "company", _("Entreprise")
        HR = "hr", _("RH")
        SITE_LIFE = "site_life", _("Vie du site")
        SAFETY = "safety", _("Sécurité")

    module = Module.ANNOUNCEMENTS
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    title = models.CharField(_("titre"), max_length=TITLE_MAX)
    category = models.CharField(
        _("catégorie"), max_length=10, choices=Category, default=Category.COMPANY
    )
    # Texte simple : affiché échappé, liens détectés, jamais de HTML libre (fiche 08).
    body = models.TextField(_("message"))
    pinned = models.BooleanField(_("épinglée"), default=False)
    author = models.ForeignKey(
        "people.Employee",
        on_delete=models.SET_NULL,
        null=True,
        related_name="+",
        verbose_name=_("auteur"),
    )
    published_at = models.DateTimeField(_("publiée le"))
    # Suppression logique : annulable 30 s, contenu gardé jusqu'à la purge (L6-09).
    deleted_at = models.DateTimeField(_("supprimée le"), null=True, blank=True)

    class Meta:
        verbose_name = _("annonce")
        verbose_name_plural = _("annonces")
        ordering = ["-pinned", "-published_at", "-pk"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(category__in=["company", "hr", "site_life", "safety"]),
                name="announcements_category_valid",
            ),
        ]

    def __str__(self):
        return self.title


class AnnouncementRead(TenantModel):
    """Lecture d'une annonce par une personne : une seule ligne, à la première ouverture."""

    announcement = models.ForeignKey(Announcement, on_delete=models.CASCADE, related_name="reads")
    employee = models.ForeignKey("people.Employee", on_delete=models.CASCADE, related_name="+")
    read_at = models.DateTimeField(_("lue le"), auto_now_add=True)

    class Meta:
        verbose_name = _("lecture d'annonce")
        verbose_name_plural = _("lectures d'annonces")
        constraints = [
            models.UniqueConstraint(
                fields=["announcement", "employee"], name="announcements_read_once"
            )
        ]
