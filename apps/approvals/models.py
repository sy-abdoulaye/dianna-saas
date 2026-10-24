"""Demandes avec circuit de validation (docs/03-modele-de-donnees.md, section Demandes).

Les transitions passent toutes par apps/approvals/workflow.py : jamais de changement de
statut direct dans une vue."""

import uuid
from datetime import date, timedelta
from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import F, Q
from django.utils.translation import gettext_lazy as _

from apps.agenda.models import CalendarEvent
from apps.core.files import get_private_storage
from apps.core.models import Module, TenantModel


class RequestStatus(models.TextChoices):
    PENDING = "pending", _("En attente")
    MANAGER_APPROVED = "manager_approved", _("Validée par le manager")
    APPROVED = "approved", _("Validée")
    REFUSED = "refused", _("Refusée")
    CANCELLED = "cancelled", _("Annulée")


ACTIVE_STATUSES = (RequestStatus.PENDING, RequestStatus.MANAGER_APPROVED, RequestStatus.APPROVED)
OPEN_STATUSES = (RequestStatus.PENDING, RequestStatus.MANAGER_APPROVED)


class ApprovalRequest(TenantModel):
    """Base abstraite : demandeur, statut, décision. `request_type` identifie le type dans
    l'historique, le journal et les routes ; `module` est le module activable concerné ;
    `calendar_kind` la projection au planning (None : pas d'événement)."""

    request_type: str = ""
    module: str = ""
    calendar_kind: str | None = None
    permission_owner_field = "requester"
    # Types validés par les RH seulement (transport M-06, matériel M-07, L5-04) : pas
    # d'étape manager, « À valider » pour les RH et administrateurs.
    hr_validated: bool = False
    # Actions de permission propres au type (apps/core/permissions.py).
    create_action = "requests.create"
    view_action = "requests.view"
    decide_action = "requests.decide"
    # Fichier joint (justificatif) : supprimé quand la demande est retirée (L5-05).
    file_field: str | None = None

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    requester = models.ForeignKey(
        "people.Employee",
        on_delete=models.CASCADE,
        related_name="+",
        verbose_name=_("demandeur"),
    )
    status = models.CharField(
        _("statut"), max_length=20, choices=RequestStatus, default=RequestStatus.PENDING
    )
    submitted_at = models.DateTimeField(_("envoyée le"))
    decided_by = models.ForeignKey(
        "people.Employee",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("décision par"),
    )
    decided_at = models.DateTimeField(_("décision le"), null=True, blank=True)
    decision_comment = models.TextField(_("motif ou commentaire"), blank=True)

    class Meta:
        abstract = True
        ordering = ["-submitted_at", "-pk"]

    # Projection au planning : (début, fin) ; None si la demande n'y apparaît pas.
    def calendar_span(self):
        return None

    @property
    def is_open(self) -> bool:
        return self.status in OPEN_STATUSES


class RequestEvent(TenantModel):
    """Historique générique d'une demande : qui, quand, quoi, commentaire."""

    class Action(models.TextChoices):
        SUBMITTED = "submitted", _("Demande envoyée")
        AUTO_APPROVED = "auto_approved", _("Validée automatiquement")
        MANAGER_APPROVED = "manager_approved", _("Validée par le manager")
        APPROVED = "approved", _("Demande validée")
        REFUSED = "refused", _("Demande refusée")
        CANCELLED = "cancelled", _("Demande annulée")
        REVERTED = "reverted", _("Décision annulée")

    request_type = models.CharField(_("type de demande"), max_length=20)
    request_id = models.PositiveBigIntegerField(_("demande"))
    actor = models.ForeignKey(
        "people.Employee",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("auteur"),
    )
    action = models.CharField(_("action"), max_length=20, choices=Action)
    comment = models.TextField(_("commentaire"), blank=True)

    class Meta:
        verbose_name = _("événement de demande")
        verbose_name_plural = _("historique des demandes")
        ordering = ["created_at", "pk"]
        indexes = [models.Index(fields=["company", "request_type", "request_id"])]

    def __str__(self):
        return self.get_action_display()


class TeleworkRequest(ApprovalRequest):
    request_type = "telework"
    module = Module.TELEWORK
    calendar_kind = CalendarEvent.Kind.TELEWORK

    date = models.DateField(_("jour"))
    comment = models.TextField(_("commentaire"), blank=True)

    class Meta(ApprovalRequest.Meta):
        verbose_name = _("demande de télétravail")
        verbose_name_plural = _("demandes de télétravail")
        constraints = [
            # Une seule demande active par jour et par personne, même en cas d'envois
            # simultanés.
            models.UniqueConstraint(
                fields=["company", "requester", "date"],
                condition=Q(status__in=["pending", "approved"]),
                name="telework_one_active_per_day",
            )
        ]

    def calendar_span(self):
        return self.date, self.date


class SummerCampaign(TenantModel):
    class Status(models.TextChoices):
        DRAFT = "draft", _("Brouillon")
        OPEN = "open", _("Ouverte")
        CLOSED = "closed", _("Close")

    label = models.CharField(_("libellé"), max_length=80)
    period_start = models.DateField(_("début de la période"))
    period_end = models.DateField(_("fin de la période"))
    deadline = models.DateField(_("date limite des vœux"))
    status = models.CharField(_("statut"), max_length=10, choices=Status, default=Status.DRAFT)
    conflict_threshold = models.PositiveSmallIntegerField(
        _("seuil de conflit (%)"),
        default=30,
        validators=[MinValueValidator(1), MaxValueValidator(100)],
    )

    class Meta:
        verbose_name = _("campagne de congés d'été")
        verbose_name_plural = _("campagnes de congés d'été")
        ordering = ["-period_start"]
        constraints = [
            models.UniqueConstraint(
                fields=["company"], condition=Q(status="open"), name="summer_campaign_one_open"
            ),
            models.CheckConstraint(
                condition=Q(period_end__gte=F("period_start")),
                name="summer_campaign_end_after_start",
            ),
        ]

    def __str__(self):
        return self.label


class LeaveRequest(ApprovalRequest):
    request_type = "leave"
    module = Module.SUMMER_LEAVE
    calendar_kind = CalendarEvent.Kind.LEAVE

    class LeaveType(models.TextChoices):
        SUMMER = "summer", _("Congés d'été")
        OTHER = "other", _("Autre absence")

    campaign = models.ForeignKey(
        SummerCampaign,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="requests",
        verbose_name=_("campagne"),
    )
    start = models.DateField(_("premier jour"))
    end = models.DateField(_("dernier jour"))
    leave_type = models.CharField(
        _("type"), max_length=10, choices=LeaveType, default=LeaveType.SUMMER
    )
    comment = models.TextField(_("commentaire"), blank=True)
    manager_decided_by = models.ForeignKey(
        "people.Employee",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("validée par le manager"),
    )
    manager_decided_at = models.DateTimeField(_("validée par le manager le"), null=True, blank=True)

    class Meta(ApprovalRequest.Meta):
        verbose_name = _("demande de congés")
        verbose_name_plural = _("demandes de congés")
        constraints = [
            models.CheckConstraint(condition=Q(end__gte=F("start")), name="leave_end_after_start"),
        ]

    def calendar_span(self):
        return self.start, self.end


class OnCallDeclaration(ApprovalRequest):
    request_type = "on_call"
    module = Module.ON_CALL
    calendar_kind = CalendarEvent.Kind.ON_CALL

    class Kind(models.TextChoices):
        ON_CALL = "on_call", _("Astreinte")
        INTERVENTION = "intervention", _("Intervention")

    kind = models.CharField(_("type"), max_length=12, choices=Kind, default=Kind.ON_CALL)
    start = models.DateField(_("début"))
    end = models.DateField(_("fin"))
    hours = models.DecimalField(
        _("durée d'intervention (heures)"), max_digits=4, decimal_places=1, null=True, blank=True
    )
    description = models.TextField(_("description"), blank=True)

    class Meta(ApprovalRequest.Meta):
        verbose_name = _("déclaration d'astreinte")
        verbose_name_plural = _("déclarations d'astreinte")
        constraints = [
            models.CheckConstraint(
                condition=Q(end__gte=F("start")), name="on_call_end_after_start"
            ),
        ]

    def calendar_span(self):
        # Seule l'astreinte est projetée au planning ; l'intervention sert à l'export paie.
        return (self.start, self.end) if self.kind == self.Kind.ON_CALL else None


def proof_path(instance, filename):
    """<company_id>/transport/<uuid>.<ext> : le nom d'origine n'est jamais utilisé (L5-01)."""
    from apps.core.files import random_name
    from apps.core.tenancy import get_current_company

    company_id = instance.company_id or get_current_company().pk
    extension = filename.rsplit(".", 1)[-1].lower()
    return random_name(f"{company_id}/transport", f"x.{extension}")


class TransportProof(ApprovalRequest):
    """Justificatif de transport (docs/modules/05-demandes.md, section Transport), validé par
    les RH. `valid_until` est calculé (fin du mois, ou 12 mois pour un abonnement annuel)."""

    request_type = "transport"
    module = Module.TRANSPORT
    hr_validated = True
    create_action = "transport.submit"
    view_action = "transport.view"
    decide_action = "transport.decide"
    file_field = "file"

    class TicketType(models.TextChoices):
        MONTHLY = "monthly", _("Abonnement mensuel")
        YEARLY = "yearly", _("Abonnement annuel")
        SINGLE = "single", _("Titre unique")

    month = models.DateField(_("mois concerné"))  # 1er du mois : début de validité
    ticket_type = models.CharField(
        _("type de titre"), max_length=10, choices=TicketType, default=TicketType.MONTHLY
    )
    amount = models.DecimalField(
        _("montant payé"),
        max_digits=7,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01")), MaxValueValidator(Decimal("1000"))],
    )
    file = models.FileField(_("justificatif"), upload_to=proof_path, storage=get_private_storage)
    file_type = models.CharField(_("type du fichier"), max_length=40)
    original_name = models.CharField(_("nom du fichier"), max_length=120, blank=True)
    valid_until = models.DateField(_("valide jusqu'au"))
    reminder_sent_at = models.DateTimeField(_("relance envoyée le"), null=True, blank=True)

    class Meta(ApprovalRequest.Meta):
        verbose_name = _("justificatif de transport")
        verbose_name_plural = _("justificatifs de transport")
        constraints = [
            models.CheckConstraint(
                condition=Q(amount__gt=0) & Q(amount__lte=1000), name="transport_amount_range"
            ),
            models.CheckConstraint(
                condition=Q(valid_until__gte=F("month")), name="transport_valid_after_month"
            ),
        ]

    def compute_validity(self):
        """Fin du mois choisi ; abonnement annuel : 12 mois à partir du mois choisi."""
        months = 12 if self.ticket_type == self.TicketType.YEARLY else 1
        year, month = divmod(self.month.month - 1 + months, 12)
        self.valid_until = date(self.month.year + year, month + 1, 1) - timedelta(days=1)
        return self.valid_until

    @property
    def is_subscription(self) -> bool:
        return self.ticket_type != self.TicketType.SINGLE


REQUEST_MODELS = {
    model.request_type: model
    for model in (TeleworkRequest, LeaveRequest, OnCallDeclaration, TransportProof)
}


def register_request_model(model):
    """Types de demande définis dans d'autres applications (matériel)."""
    REQUEST_MODELS[model.request_type] = model
    _register_notification_source(model)
    return model


def _register_notification_source(model) -> None:
    """Notifications d'une demande : leur e-mail ne part pas si la demande a disparu."""
    from apps.core import notifications

    notifications.register_source(
        model.request_type, lambda pk: model.objects.filter(pk=pk).exists()
    )


for _model in REQUEST_MODELS.values():
    _register_notification_source(_model)
