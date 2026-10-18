import uuid

from django.conf import settings
from django.db import models
from django.db.models.functions import Lower
from django.utils.translation import gettext_lazy as _

from apps.core.models import TenantModel


class Role(models.TextChoices):
    """Profil d'accès (V-06). Les droits « Équipe » ne dépendent pas du profil mais du fait
    d'avoir des collaborateurs directs (L1-02)."""

    EMPLOYEE = "employee", _("Salarié")
    MANAGER = "manager", _("Manager")
    HR = "hr", _("Ressources humaines")
    ADMIN = "admin", _("Administrateur")


class EmployeeStatus(models.TextChoices):
    ACTIVE = "active", _("Actif")
    UPCOMING = "upcoming", _("Arrivée prochaine")
    LEFT = "left", _("Parti")


class ContractType(models.TextChoices):
    CDI = "cdi", _("CDI")
    CDD = "cdd", _("CDD")
    APPRENTICESHIP = "apprenticeship", _("Alternance")
    INTERNSHIP = "internship", _("Stage")


class WorkTime(models.TextChoices):
    FULL_35 = "full_35", _("Temps plein (35 h)")
    PART_28 = "part_28", _("Temps partiel (28 h)")
    DAYS_PACKAGE = "days_package", _("Forfait jours")


# Statuts « en poste » : l'arrivée prochaine est comptée avec les actifs (L1-04).
IN_POST_STATUSES = (EmployeeStatus.ACTIVE, EmployeeStatus.UPCOMING)


class Employee(TenantModel):
    """Fiche salarié. Le compte de connexion (User) est séparé (T-09) et reste nul tant que
    l'invitation n'est pas acceptée."""

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="employee",
        verbose_name=_("compte"),
    )
    first_name = models.CharField(_("prénom"), max_length=60)
    last_name = models.CharField(_("nom"), max_length=60)
    email = models.EmailField(_("e-mail professionnel"))
    phone = models.CharField(_("téléphone"), max_length=30, blank=True)
    office = models.CharField(_("bureau"), max_length=60, blank=True)
    job_title = models.CharField(_("poste"), max_length=120, blank=True)
    # Obligatoires dans le formulaire de fiche (lot 2) ; nuls permis pour le premier
    # administrateur, créé avant les services et les sites.
    service = models.ForeignKey(
        "core.Service", on_delete=models.RESTRICT, null=True, blank=True, verbose_name=_("service")
    )
    site = models.ForeignKey(
        "core.Site", on_delete=models.RESTRICT, null=True, blank=True, verbose_name=_("site")
    )
    manager = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reports",
        verbose_name=_("manager"),
    )
    role = models.CharField(_("profil d'accès"), max_length=10, choices=Role, default=Role.EMPLOYEE)
    status = models.CharField(
        _("statut"), max_length=10, choices=EmployeeStatus, default=EmployeeStatus.ACTIVE
    )
    arrival_date = models.DateField(_("date d'arrivée"), null=True, blank=True)
    departure_date = models.DateField(_("date de départ"), null=True, blank=True)
    contract_type = models.CharField(_("contrat"), max_length=16, choices=ContractType, blank=True)
    work_time = models.CharField(_("temps de travail"), max_length=16, choices=WorkTime, blank=True)
    registration_number = models.CharField(_("matricule"), max_length=30, blank=True)
    telework_days_override = models.PositiveSmallIntegerField(
        _("dérogation au quota de télétravail"), null=True, blank=True
    )

    class Meta:
        verbose_name = _("fiche salarié")
        verbose_name_plural = _("fiches salarié")
        ordering = ["last_name", "first_name"]
        constraints = [
            models.UniqueConstraint(
                Lower("email"), "company", name="people_employee_email_ci_unique"
            ),
            models.UniqueConstraint(
                fields=["company", "registration_number"],
                condition=~models.Q(registration_number=""),
                name="people_employee_registration_unique",
            ),
        ]
        indexes = [
            models.Index(fields=["company", "last_name"]),
            models.Index(fields=["company", "service"]),
            models.Index(fields=["company", "manager"]),
        ]

    def __str__(self):
        return self.full_name

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    @property
    def can_sign_in(self) -> bool:
        """Un salarié parti n'a plus accès (compte désactivé à l'archivage)."""
        return self.status != EmployeeStatus.LEFT and bool(self.user_id and self.user.is_active)

    @property
    def is_hr_or_admin(self) -> bool:
        return self.role in (Role.HR, Role.ADMIN)

    @property
    def requires_two_factor(self) -> bool:
        return self.is_hr_or_admin

    @property
    def has_reports(self) -> bool:
        """Droits « Équipe » : avoir au moins un collaborateur direct en poste (L1-02)."""
        cached = getattr(self, "_has_reports", None)
        if cached is None:
            cached = Employee.all_companies.filter(
                company_id=self.company_id, manager_id=self.pk, status__in=IN_POST_STATUSES
            ).exists()
            self._has_reports = cached
        return cached

    def save(self, *args, **kwargs):
        self.email = (self.email or "").strip()
        super().save(*args, **kwargs)
