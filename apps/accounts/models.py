from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.models import TenantModel, Timestamped


def normalize_email(email: str) -> str:
    """Les adresses sont comparées sans tenir compte de la casse : on les stocke en minuscules."""
    return (email or "").strip().lower()


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("L'adresse e-mail est obligatoire.")
        user = self.model(email=normalize_email(email), **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if not extra_fields["is_staff"] or not extra_fields["is_superuser"]:
            raise ValueError("Un super-utilisateur doit avoir is_staff et is_superuser.")
        return self._create_user(email, password, **extra_fields)

    def get_by_natural_key(self, username):
        return self.get(email=normalize_email(username))


class User(Timestamped, AbstractBaseUser, PermissionsMixin):
    """Identité de connexion (T-09, L0-01). La fiche RH est le modèle Employee (lot 1).

    `is_staff` donne accès à l'administration Django réservée à l'équipe Dianna
    (super-administrateur éditeur, T-22)."""

    class Theme(models.TextChoices):
        SYSTEM = "system", _("Système")
        LIGHT = "light", _("Clair")
        DARK = "dark", _("Sombre")

    email = models.EmailField(_("adresse e-mail"), unique=True)
    is_active = models.BooleanField(_("actif"), default=True)
    is_staff = models.BooleanField(
        _("équipe Dianna"),
        default=False,
        help_text=_("Accès à l'administration de l'éditeur (super-administration)."),
    )
    theme = models.CharField(_("thème"), max_length=6, choices=Theme, default=Theme.SYSTEM)

    objects = UserManager()

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        verbose_name = _("compte")
        verbose_name_plural = _("comptes")
        constraints = [
            models.UniqueConstraint(Lower("email"), name="accounts_user_email_ci_unique"),
        ]

    def __str__(self):
        return self.email

    @property
    def is_platform_staff(self) -> bool:
        """Super-administrateur éditeur (docs/03-modele-de-donnees.md)."""
        return self.is_staff

    def clean(self):
        super().clean()
        self.email = normalize_email(self.email)


class Invitation(TenantModel):
    """Invitation à créer son mot de passe (7 jours). Seule l'empreinte du jeton est stockée."""

    VALIDITY_DAYS = 7

    employee = models.ForeignKey(
        "people.Employee",
        on_delete=models.CASCADE,
        related_name="invitations",
        verbose_name=_("fiche"),
    )
    token_hash = models.CharField(max_length=64, unique=True, editable=False)
    expires_at = models.DateTimeField(_("expire le"))
    accepted_at = models.DateTimeField(_("acceptée le"), null=True, blank=True)
    revoked_at = models.DateTimeField(_("remplacée le"), null=True, blank=True)
    renewal_requested_at = models.DateTimeField(
        _("nouvelle invitation demandée le"), null=True, blank=True
    )
    sent_by = models.ForeignKey(
        "people.Employee",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("envoyée par"),
    )

    class Meta:
        verbose_name = _("invitation")
        verbose_name_plural = _("invitations")
        ordering = ["-created_at"]

    def __str__(self):
        return f"Invitation {self.employee}"

    @property
    def is_usable(self) -> bool:
        return (
            self.accepted_at is None
            and self.revoked_at is None
            and self.expires_at > timezone.now()
            and self.employee.user_id is None
        )
