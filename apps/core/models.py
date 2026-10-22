from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator
from django.db import models
from django.db.models.functions import Lower
from django.utils.translation import gettext_lazy as _

from apps.core.files import get_private_storage
from apps.core.tenancy import CompanyMismatchError, get_current_company


def company_logo_path(instance, filename):
    from apps.core.files import random_name

    return random_name(f"{instance.pk}/logo", filename)


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
    logo = models.ImageField(
        _("logo"),
        upload_to=company_logo_path,
        storage=get_private_storage,
        blank=True,
    )

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
    """Queryset lié à l'entreprise courante au moment de sa construction.

    Le filtre `company=` est posé à la construction (TenantManager.get_queryset) et
    l'entreprise est mémorisée. À l'évaluation (lecture, comptage, mise à jour, suppression,
    emploi en sous-requête), l'entreprise courante doit être présente et identique :
    - aucune entreprise courante → NoCurrentCompanyError ;
    - autre entreprise, ou queryset construit sans entreprise → CompanyMismatchError.
    Django construit des querysets dès l'import (champs de ModelForm) : ils peuvent exister,
    mais jamais être lus dans une requête. D'où la règle de CLAUDE.md : pas de queryset métier
    au niveau d'une classe, toujours dans get_queryset ou __init__."""

    _bound_company_id = None
    _built_without_company = False

    def _clone(self):
        clone = super()._clone()
        clone._bound_company_id = self._bound_company_id
        clone._built_without_company = self._built_without_company
        return clone

    def _guard(self):
        current = get_current_company()  # lève NoCurrentCompanyError
        if self._built_without_company:
            raise CompanyMismatchError(
                f"Queryset {self.model.__name__} construit sans entreprise courante puis évalué "
                "dans une requête : construisez-le dans get_queryset ou __init__."
            )
        if self._bound_company_id is not None and self._bound_company_id != current.pk:
            raise CompanyMismatchError(
                f"Queryset {self.model.__name__} construit pour une autre entreprise que "
                "l'entreprise courante."
            )

    def resolve_expression(self, *args, **kwargs):
        # Sous-requête (filter(pk__in=queryset), Subquery…) : même contrôle qu'une lecture.
        self._guard()
        return super().resolve_expression(*args, **kwargs)

    def aiterator(self, *args, **kwargs):
        self._guard()
        return super().aiterator(*args, **kwargs)

    def _fetch_all(self):
        self._guard()
        super()._fetch_all()

    def iterator(self, *args, **kwargs):
        self._guard()
        return super().iterator(*args, **kwargs)

    def count(self):
        self._guard()
        return super().count()

    def exists(self):
        self._guard()
        return super().exists()

    def aggregate(self, *args, **kwargs):
        self._guard()
        return super().aggregate(*args, **kwargs)

    def update(self, **kwargs):
        self._guard()
        return super().update(**kwargs)

    def delete(self):
        self._guard()
        return super().delete()


class TenantManager(models.Manager.from_queryset(TenantQuerySet)):
    """Filtre sur l'entreprise courante et lie le queryset à cette entreprise (voir
    TenantQuerySet). Sans entreprise, le queryset est vide et illisible."""

    use_in_migrations = False

    def get_queryset(self):
        queryset = super().get_queryset()
        company = get_current_company(required=False)
        if company is None:
            queryset = queryset.none()
            queryset._built_without_company = True
            return queryset
        queryset = queryset.filter(company=company)
        queryset._bound_company_id = company.pk
        return queryset


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
        """Clés étrangères et relations un-à-un vers un objet métier (les relations
        plusieurs-à-plusieurs sont contrôlées par le signal m2m_changed)."""
        for field in self._meta.concrete_fields:
            if (
                field.is_relation
                and (field.many_to_one or field.one_to_one)
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
    # Jours fériés d'Alsace-Moselle (Vendredi saint, 26 décembre), L4-02.
    alsace_moselle = models.BooleanField(_("jours fériés d'Alsace-Moselle"), default=False)

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
    permission_owner_field = "recipient"
    text = models.CharField(_("texte"), max_length=255)
    url = models.CharField(_("lien"), max_length=255, blank=True)
    kind = models.CharField(_("type"), max_length=10, choices=Kind, default=Kind.INFO)
    read_at = models.DateTimeField(_("lue le"), null=True, blank=True)
    email_sent_at = models.DateTimeField(_("e-mail envoyé le"), null=True, blank=True)
    # Objet de l'e-mail, s'il y en a un : le corps est construit au moment de l'envoi.
    email_subject = models.CharField(_("objet de l'e-mail"), max_length=150, blank=True)
    # Objet concerné (demande…) : une transition retire les notifications devenues fausses.
    source_type = models.CharField(_("type d'objet"), max_length=20, blank=True)
    source_id = models.PositiveBigIntegerField(_("objet"), null=True, blank=True)

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


def check_m2m_same_company(sender, instance, action, reverse, model, pk_set, **kwargs):
    """Relations plusieurs-à-plusieurs : refuse d'ajouter un objet d'une autre entreprise."""
    if action != "pre_add" or not pk_set:
        return
    if not isinstance(instance, TenantModel) or not issubclass(model, TenantModel):
        return
    foreign = model.all_companies.filter(pk__in=pk_set).exclude(company_id=instance.company_id)
    if foreign.exists():
        raise ValidationError(_("Cet élément n'appartient pas à la même entreprise."))


class RateLimitCounter(models.Model):
    """Compteur de limite de fréquence (L4-17, L1-16) : une ligne par clé et par fenêtre.

    Modèle technique de la plateforme, sans entreprise : la clé est une empreinte HMAC (jamais
    une adresse IP ni une adresse e-mail en clair). Incrémenté en une seule requête atomique
    (apps/core/ratelimit.py) ; les fenêtres expirées sont purgées par `purge_task_results`."""

    key = models.CharField(_("clé (empreinte)"), max_length=64)
    window_start = models.DateTimeField(_("début de la fenêtre"))
    count = models.PositiveIntegerField(_("nombre"), default=0)

    class Meta:
        verbose_name = _("compteur de limite")
        verbose_name_plural = _("compteurs de limite")
        constraints = [
            models.UniqueConstraint(fields=["key", "window_start"], name="core_ratelimit_unique")
        ]
        indexes = [models.Index(fields=["window_start"], name="core_ratelimit_window")]

    def __str__(self):
        return f"{self.key[:8]}… {self.count}"
