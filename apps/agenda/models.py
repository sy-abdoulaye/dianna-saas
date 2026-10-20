"""Événement de calendrier commun (docs/02-architecture.md) : projection d'une demande dans
le planning. Créé dès l'envoi (en attente, hachuré), validé à la décision finale, supprimé en
cas de refus ou d'annulation. Le planning (lot 4) ne lit que cette table."""

from django.db import models
from django.db.models import F, Q
from django.utils.translation import gettext_lazy as _

from apps.core.models import TenantModel


class CalendarEvent(TenantModel):
    class Kind(models.TextChoices):
        TELEWORK = "telework", _("Télétravail")
        LEAVE = "leave", _("Congés")
        ON_CALL = "on_call", _("Astreinte")

    class Status(models.TextChoices):
        PENDING = "pending", _("En attente")
        APPROVED = "approved", _("Validé")

    employee = models.ForeignKey(
        "people.Employee",
        on_delete=models.CASCADE,
        related_name="calendar_events",
        verbose_name=_("collaborateur"),
    )
    kind = models.CharField(_("type"), max_length=10, choices=Kind)
    start = models.DateField(_("début"))
    end = models.DateField(_("fin"))
    status = models.CharField(_("statut"), max_length=10, choices=Status, default=Status.PENDING)
    source_type = models.CharField(_("type de demande"), max_length=20)
    source_id = models.PositiveBigIntegerField(_("demande"))
    permission_owner_field = "employee"

    class Meta:
        verbose_name = _("événement de calendrier")
        verbose_name_plural = _("événements de calendrier")
        ordering = ["start", "employee_id"]
        indexes = [
            models.Index(fields=["company", "start", "end"]),
            models.Index(fields=["employee", "start"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "source_type", "source_id"], name="agenda_event_one_per_source"
            ),
            models.CheckConstraint(
                condition=Q(end__gte=F("start")), name="agenda_event_end_after_start"
            ),
        ]

    def __str__(self):
        return f"{self.get_kind_display()} {self.start}"
