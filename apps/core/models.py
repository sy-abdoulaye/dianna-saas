from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator
from django.db import models
from django.db.models.functions import Lower
from django.utils.translation import gettext_lazy as _

from apps.core.tenancy import get_current_company


class Timestamped(models.Model):
    """Horodatage de création et de modification, commun à tous les modèles (sauf exceptions
    documentées dans docs/03-modele-de-donnees.md, comme les réponses anonymes)."""

    created_at = models.DateTimeField(_("créé le"), auto_now_add=True)
    updated_at = models.DateTimeField(_("modifié le"), auto_now=True)

    class Meta:
        abstract = True


class Company(Timestamped):
    """Entreprise cliente (tenant). Pas de champ company : c'est la racine."""

    class Status(models.TextChoices):
        ACTIVE = "active", _("Active")
        SUSPENDED = "suspended", _("Suspendue")

    name = models.CharField(_("nom"), max_length=120)
    slug = models.SlugField(
        _("sous-domaine"),
        unique=True,
        max_length=63,
        help_text=_("Adresse de l'espace : <sous-domaine>.dianna.fr"),
    )
    status = models.CharField(_("statut"), max_length=10, choices=Status, default=Status.ACTIVE)
    telework_max_per_week = models.PositiveSmallIntegerField(
        _("jours de télétravail par semaine"), default=2, validators=[MaxValueValidator(5)]
    )
    telework_auto_approve = models.BooleanField(
        _("validation automatique du télétravail"), default=False
    )
    summer_leave_hr_step = models.BooleanField(
        _("validation finale RH des congés d'été"), default=True
    )
    timezone = models.CharField(_("fuseau horaire"), max_length=40, default="Europe/Paris")

    class Meta:
        verbose_name = _("entreprise")
        verbose_name_plural = _("entreprises")
        ordering = ["name"]

    RESERVED_SLUGS = frozenset({"www", "admin", "api", "static", "media", "mail", "support"})

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        if self.slug in self.RESERVED_SLUGS:
            raise ValidationError({"slug": _("Ce sous-domaine est réservé.")})

    @property
    def is_active(self) -> bool:
        return self.status == self.Status.ACTIVE


class TenantQuerySet(models.QuerySet):
    pass


class TenantManager(models.Manager.from_queryset(TenantQuerySet)):
    """Filtre automatiquement sur l'entreprise courante ; lève NoCurrentCompanyError sans elle."""

    use_in_migrations = False

    def get_queryset(self):
        return super().get_queryset().filter(company=get_current_company())


class TenantModel(Timestamped):
    """Base de tout modèle métier (règle 1 de CLAUDE.md).

    - `objects` ne voit que l'entreprise courante ;
    - `all_companies` est réservé aux commandes de plateforme, à l'administration éditeur et
      aux fabriques de test, jamais aux vues ;
    - `save()` renseigne l'entreprise depuis le contexte, refuse une incohérence et vérifie
      que chaque clé étrangère vers un objet métier pointe dans la même entreprise.
    """

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        editable=False,
        related_name="+",
        verbose_name=_("entreprise"),
    )

    objects = TenantManager()
    all_companies = models.Manager()  # noqa: DJ012 (gestionnaires avant la Meta)

    class Meta:
        abstract = True
        default_manager_name = "objects"
        base_manager_name = "all_companies"

    def _tenant_foreign_keys(self):
        for field in self._meta.concrete_fields:
            if (
                field.is_relation
                and field.many_to_one
                and field.name != "company"
                and issubclass(field.related_model, TenantModel)
            ):
                yield field

    def check_same_company(self):
        """Toutes les clés étrangères métier pointent vers la même entreprise."""
        errors = {}
        for field in self._tenant_foreign_keys():
            related_id = getattr(self, field.attname)
            if related_id is None:
                continue
            cached = field.get_cached_value(self, default=None)
            if cached is not None and cached.pk == related_id:
                related_company = cached.company_id
            else:
                related_company = (
                    field.related_model.all_companies.filter(pk=related_id)
                    .values_list("company_id", flat=True)
                    .first()
                )
            if related_company != self.company_id:
                errors[field.name] = _("Cet élément n'appartient pas à la même entreprise.")
        if errors:
            raise ValidationError(errors)

    def clean(self):
        super().clean()
        if self.company_id is None:
            self.company = get_current_company()
        self.check_same_company()

    def save(self, *args, **kwargs):  # noqa: DJ012
        current = get_current_company(required=False)
        if self.company_id is None:
            if current is None:
                get_current_company()  # lève NoCurrentCompanyError
            self.company = current
        elif current is not None and current.pk != self.company_id:
            raise ValidationError(
                _("Écriture refusée : l'objet appartient à une autre entreprise.")
            )
        self.check_same_company()
        super().save(*args, **kwargs)


class Module(models.TextChoices):
    """Modules activables (CompanyModule). Le socle, l'annuaire (L1-05) et l'administration ne
    sont pas désactivables."""

    PLANNING = "planning", _("Planning")
    TELEWORK = "telework", _("Télétravail")
    SUMMER_LEAVE = "summer_leave", _("Congés estivaux")
    ON_CALL = "on_call", _("Astreintes")
    TRANSPORT = "transport", _("Transport")
    EQUIPMENT = "equipment", _("Matériel")
    ANNOUNCEMENTS = "announcements", _("Communication interne")
    SURVEYS = "surveys", _("Questionnaires")
    CAREERS = "careers", _("Carrière et évaluations")
    INTERVENTIONS = "interventions", _("Suivi d'intervention")


class CompanyModule(TenantModel):
    module = models.CharField(_("module"), max_length=20, choices=Module)
    enabled = models.BooleanField(_("activé"), default=True)

    class Meta:
        verbose_name = _("module")
        verbose_name_plural = _("modules")
        constraints = [
            models.UniqueConstraint(fields=["company", "module"], name="core_companymodule_unique")
        ]

    def __str__(self):
        return self.get_module_display()


class Site(TenantModel):
    name = models.CharField(_("nom"), max_length=80)
    address = models.CharField(_("adresse"), max_length=255, blank=True)

    class Meta:
        verbose_name = _("site")
        verbose_name_plural = _("sites")
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(Lower("name"), "company", name="core_site_name_ci_unique")
        ]

    def __str__(self):
        return self.name


class Service(TenantModel):
    name = models.CharField(_("nom"), max_length=80)

    class Meta:
        verbose_name = _("service")
        verbose_name_plural = _("services")
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(Lower("name"), "company", name="core_service_name_ci_unique")
        ]

    def __str__(self):
        return self.name


class AuditLog(TenantModel):
    """Journal d'activité de l'entreprise (docs/02-architecture.md, section Sécurité).

    `summary` ne contient jamais de donnée sensible (pas de contenu de fiche, pas de motif)."""

    actor = models.ForeignKey(
        "people.Employee",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("auteur"),
        help_text=_("Vide pour une action de la plateforme ou automatique."),
    )
    action = models.CharField(_("action"), max_length=60)
    target_type = models.CharField(_("type d'objet"), max_length=60, blank=True)
    target_id = models.CharField(_("identifiant de l'objet"), max_length=64, blank=True)
    summary = models.CharField(_("résumé"), max_length=255)
    ip = models.GenericIPAddressField(_("adresse IP"), null=True, blank=True)

    class Meta:
        verbose_name = _("entrée du journal")
        verbose_name_plural = _("journal d'activité")
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["company", "created_at"])]

    def __str__(self):
        return self.summary


class Notification(TenantModel):
    class Kind(models.TextChoices):
        INFO = "info", _("Information")
        REQUEST = "request", _("Demande à valider")
        DECISION = "decision", _("Décision")
        ACCOUNT = "account", _("Compte")

    recipient = models.ForeignKey(
        "people.Employee",
        on_delete=models.CASCADE,
        related_name="notifications",
        verbose_name=_("destinataire"),
    )
    text = models.CharField(_("texte"), max_length=255)
    url = models.CharField(_("lien"), max_length=255, blank=True)
    kind = models.CharField(_("type"), max_length=10, choices=Kind, default=Kind.INFO)
    read_at = models.DateTimeField(_("lue le"), null=True, blank=True)
    email_sent_at = models.DateTimeField(_("e-mail envoyé le"), null=True, blank=True)

    class Meta:
        verbose_name = _("notification")
        verbose_name_plural = _("notifications")
        ordering = ["-created_at", "-pk"]
        indexes = [models.Index(fields=["recipient", "read_at"])]

    def __str__(self):
        return self.text

    @property
    def is_unread(self) -> bool:
        return self.read_at is None
