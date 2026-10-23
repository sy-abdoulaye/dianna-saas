"""Suivi du matériel (docs/modules/07-materiel.md).

Un équipement n'a qu'un détenteur à la fois (L5-08), garanti en base :
- une seule attribution ouverte par équipement (index unique partiel) ;
- « Attribué » ⇔ un détenteur ; « En stock » et « Retiré » : aucun détenteur ; « En
  réparation » : avec ou sans détenteur (envoi en réparation depuis un signalement) ;
et par les services, qui verrouillent l'équipement avant chaque changement.
"""

import uuid

from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from apps.approvals.models import ApprovalRequest, register_request_model
from apps.core.models import Module, TenantModel


class EquipmentKind(models.TextChoices):
    LAPTOP = "laptop", _("Ordinateur portable")
    SCREEN = "screen", _("Écran")
    HEADSET = "headset", _("Casque audio")
    PHONE = "phone", _("Téléphone")
    OTHER = "other", _("Autre")


class EquipmentItem(TenantModel):
    class Status(models.TextChoices):
        IN_STOCK = "in_stock", _("En stock")
        ASSIGNED = "assigned", _("Attribué")
        REPAIR = "repair", _("En réparation")
        RETIRED = "retired", _("Retiré")

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    kind = models.CharField(_("type"), max_length=10, choices=EquipmentKind)
    model = models.CharField(_("modèle"), max_length=120)
    serial_number = models.CharField(_("n° de série"), max_length=60)
    status = models.CharField(_("état"), max_length=10, choices=Status, default=Status.IN_STOCK)
    holder = models.ForeignKey(
        "people.Employee",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="equipment",
        verbose_name=_("détenteur"),
    )
    assigned_at = models.DateTimeField(_("attribué le"), null=True, blank=True)
    permission_owner_field = "holder"

    class Meta:
        verbose_name = _("équipement")
        verbose_name_plural = _("équipements")
        ordering = ["kind", "model", "serial_number"]
        constraints = [
            # Valeur normalisée par le service (NFKC, sans espaces, majuscules, L5-09).
            models.UniqueConstraint(
                fields=["company", "serial_number"], name="equipment_serial_unique"
            ),
            models.CheckConstraint(
                condition=(
                    Q(status="assigned", holder__isnull=False)
                    | Q(status__in=["in_stock", "retired"], holder__isnull=True)
                    | Q(status="repair")
                ),
                name="equipment_holder_matches_status",
            ),
        ]

    def __str__(self):
        return f"{self.get_kind_display()} {self.serial_number}"


class EquipmentRequest(ApprovalRequest):
    """Demande de matériel, validée par les RH (M-07, L5-04), moteur commun des demandes."""

    request_type = "equipment"
    module = Module.EQUIPMENT
    hr_validated = True
    create_action = "equipment.request"
    view_action = "equipment.view"
    decide_action = "equipment.decide"

    kind = models.CharField(_("équipement"), max_length=10, choices=EquipmentKind)
    reason = models.TextField(_("motif"))

    class Meta(ApprovalRequest.Meta):
        verbose_name = _("demande de matériel")
        verbose_name_plural = _("demandes de matériel")


register_request_model(EquipmentRequest)


class EquipmentAssignment(TenantModel):
    """Historique des attributions ; une seule ouverte par équipement (L5-08)."""

    item = models.ForeignKey(EquipmentItem, on_delete=models.CASCADE, related_name="assignments")
    employee = models.ForeignKey(
        "people.Employee", on_delete=models.RESTRICT, related_name="+", verbose_name=_("détenteur")
    )
    assigned_at = models.DateTimeField(_("attribué le"))
    returned_at = models.DateTimeField(_("restitué le"), null=True, blank=True)
    assigned_by = models.ForeignKey(
        "people.Employee", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    request = models.ForeignKey(
        EquipmentRequest,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assignments",
    )
    permission_owner_field = "employee"

    class Meta:
        verbose_name = _("attribution")
        verbose_name_plural = _("attributions")
        ordering = ["-assigned_at", "-pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["item"],
                condition=Q(returned_at__isnull=True),
                name="equipment_one_open_assignment",
            ),
            models.UniqueConstraint(
                fields=["request"],
                condition=Q(request__isnull=False),
                name="equipment_one_assignment_per_request",
            ),
        ]


class EquipmentIssue(TenantModel):
    class Status(models.TextChoices):
        OPEN = "open", _("Ouvert")
        CLOSED = "closed", _("Clos")

    item = models.ForeignKey(EquipmentItem, on_delete=models.CASCADE, related_name="issues")
    reported_by = models.ForeignKey(
        "people.Employee", on_delete=models.RESTRICT, related_name="+", verbose_name=_("auteur")
    )
    description = models.TextField(_("description"))
    status = models.CharField(_("état"), max_length=10, choices=Status, default=Status.OPEN)
    closed_by = models.ForeignKey(
        "people.Employee", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    closed_at = models.DateTimeField(_("clos le"), null=True, blank=True)
    resolution = models.TextField(_("résolution"), blank=True)
    permission_owner_field = "reported_by"

    class Meta:
        verbose_name = _("signalement")
        verbose_name_plural = _("signalements")
        ordering = ["-created_at", "-pk"]


class EquipmentEvent(TenantModel):
    """Historique complet par équipement : attributions, restitutions, réparations,
    signalements, entrée et sortie du parc."""

    class Action(models.TextChoices):
        ADDED = "added", _("Ajouté au parc")
        ASSIGNED = "assigned", _("Attribué")
        RETURNED = "returned", _("Restitué")
        REPAIR = "repair", _("Envoyé en réparation")
        BACK = "back", _("Retour de réparation")
        ISSUE = "issue", _("Problème signalé")
        ISSUE_CLOSED = "issue_closed", _("Signalement clos")
        RETIRED = "retired", _("Retiré du parc")
        UNDONE = "undone", _("Attribution annulée")
        REPAIR_UNDONE = "repair_undone", _("Envoi en réparation annulé")

    item = models.ForeignKey(EquipmentItem, on_delete=models.CASCADE, related_name="events")
    action = models.CharField(_("action"), max_length=15, choices=Action)
    actor = models.ForeignKey(
        "people.Employee", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    employee = models.ForeignKey(
        "people.Employee", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    comment = models.TextField(_("commentaire"), blank=True)

    class Meta:
        verbose_name = _("événement d'équipement")
        verbose_name_plural = _("historique du matériel")
        ordering = ["-created_at", "-pk"]
