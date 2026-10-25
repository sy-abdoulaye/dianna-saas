"""Suivi d'intervention (docs/modules/11-interventions.md).

Un compte rendu par personne, intervention et mois (M-11), garanti en base. `version`
augmente à chaque enregistrement : un enregistrement fait depuis une version dépassée (autre
onglet) est refusé, rien n'est écrasé (L7, enregistrement automatique).
"""

import uuid

from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Lower
from django.utils.translation import gettext_lazy as _

from apps.core.models import TenantModel

TEXT_MAX = 5000


class Mission(TenantModel):
    """Intervention (mission client ou projet), créée au premier compte rendu qui la cite."""

    name = models.CharField(_("nom"), max_length=160)
    client = models.CharField(_("client"), max_length=120, blank=True)
    active = models.BooleanField(_("active"), default=True)

    class Meta:
        verbose_name = _("intervention")
        verbose_name_plural = _("interventions")
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                Lower("name"), "company", name="interventions_mission_name_ci_unique"
            )
        ]

    def __str__(self):
        return self.name


class ReportStatus(models.TextChoices):
    DRAFT = "draft", _("Brouillon")
    SUBMITTED = "submitted", _("Envoyé")
    APPROVED = "approved", _("Validé")
    CHANGES_REQUESTED = "changes_requested", _("Complément demandé")


EDITABLE_STATUSES = (ReportStatus.DRAFT, ReportStatus.CHANGES_REQUESTED)


class Visibility(models.TextChoices):
    PLANNED_END = "planned_end", _("Fin prévue")
    EXTENSION_LIKELY = "extension_likely", _("Prolongation probable")
    EXTENSION_CONFIRMED = "extension_confirmed", _("Prolongation confirmée")
    UNCERTAIN = "uncertain", _("Incertaine")


class InterventionReport(TenantModel):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    employee = models.ForeignKey(
        "people.Employee",
        on_delete=models.RESTRICT,
        related_name="intervention_reports",
        verbose_name=_("collaborateur"),
    )
    mission = models.ForeignKey(
        Mission, on_delete=models.RESTRICT, related_name="reports", verbose_name=_("intervention")
    )
    period = models.DateField(_("période"))  # 1er du mois
    status = models.CharField(
        _("statut"), max_length=20, choices=ReportStatus, default=ReportStatus.DRAFT
    )
    visibility = models.CharField(_("visibilité"), max_length=20, choices=Visibility, blank=True)
    planned_end = models.DateField(_("date de fin prévue"), null=True, blank=True)
    extension_wanted = models.BooleanField(_("prolongation souhaitée"), default=False)
    extension_until = models.DateField(_("prolongation jusqu'au"), null=True, blank=True)
    follow_up = models.TextField(
        _("points de suivi, risques et besoins"), max_length=TEXT_MAX, blank=True
    )
    reviewer_note = models.TextField(_("remarque du manager"), max_length=TEXT_MAX, blank=True)
    submitted_at = models.DateTimeField(_("envoyé le"), null=True, blank=True)
    version = models.PositiveIntegerField(_("version"), default=1)
    permission_owner_field = "employee"

    class Meta:
        verbose_name = _("compte rendu d'intervention")
        verbose_name_plural = _("comptes rendus d'intervention")
        ordering = ["-period", "-pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "employee", "mission", "period"],
                name="interventions_one_report_per_period",
            ),
            models.CheckConstraint(
                condition=Q(period__day=1), name="interventions_period_first_day"
            ),
            models.CheckConstraint(
                condition=Q(extension_until__isnull=True)
                | Q(planned_end__isnull=True)
                | Q(extension_until__gt=F("planned_end")),
                name="interventions_extension_after_end",
            ),
        ]

    def __str__(self):
        return f"{self.mission} · {self.period:%Y-%m}"

    @property
    def is_editable(self) -> bool:
        return self.status in EDITABLE_STATUSES


class ReportItem(TenantModel):
    class Section(models.TextChoices):
        DONE = "done", _("Travail réalisé")
        NEXT = "next", _("Travail prévu")

    report = models.ForeignKey(InterventionReport, on_delete=models.CASCADE, related_name="items")
    section = models.CharField(_("section"), max_length=4, choices=Section)
    order = models.PositiveSmallIntegerField(_("ordre"), default=0)
    description = models.TextField(_("descriptif"), max_length=TEXT_MAX, blank=True)
    difficulties = models.TextField(_("difficultés rencontrées"), max_length=TEXT_MAX, blank=True)
    solutions = models.TextField(_("solutions proposées"), max_length=TEXT_MAX, blank=True)
    completion = models.PositiveSmallIntegerField(_("réalisation"), null=True, blank=True)
    due_date = models.DateField(_("délai"), null=True, blank=True)
    comments = models.TextField(_("commentaires"), max_length=TEXT_MAX, blank=True)

    class Meta:
        ordering = ["section", "order", "pk"]
        constraints = [
            models.CheckConstraint(
                condition=Q(completion__isnull=True) | Q(completion__lte=100),
                name="interventions_completion_range",
            ),
        ]


class ReportEvent(TenantModel):
    class Action(models.TextChoices):
        SUBMITTED = "submitted", _("Compte rendu envoyé")
        APPROVED = "approved", _("Compte rendu validé")
        CHANGES_REQUESTED = "changes_requested", _("Complément demandé")
        REVERTED = "reverted", _("Décision annulée")

    report = models.ForeignKey(InterventionReport, on_delete=models.CASCADE, related_name="events")
    actor = models.ForeignKey(
        "people.Employee", on_delete=models.SET_NULL, null=True, related_name="+"
    )
    action = models.CharField(_("action"), max_length=20, choices=Action)
    comment = models.TextField(_("commentaire"), max_length=TEXT_MAX, blank=True)

    class Meta:
        ordering = ["created_at", "pk"]
