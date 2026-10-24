"""Réglages communs à tous les environnements (T-19)."""

from pathlib import Path

import environ
from django.contrib.messages import constants as messages
from django.utils.csp import CSP

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env", overwrite=False)

SECRET_KEY = env("SECRET_KEY")
DEBUG = env.bool("DEBUG", default=False)
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[])

# Le guide de style n'est monté qu'en développement, et jamais si DEBUG est faux.
STYLEGUIDE_ENABLED = False

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "config.apps.StaticFilesConfig",
    "django_htmx",
    "django_tasks_db",
    "allauth",
    "allauth.account",
    "allauth.mfa",
    "apps.core",
    "apps.accounts",
    "apps.people",
    "apps.agenda",
    "apps.approvals",
    "apps.planning",
    "apps.equipment",
    "apps.announcements",
    "apps.surveys",
    "apps.dashboard",
    "apps.administration",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    # Hôte → entreprise courante et routes (vitrine, éditeur, espace client).
    "apps.core.middleware.CompanyMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "apps.core.middleware.EmployeeMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "apps.accounts.middleware.TwoFactorEnrollmentMiddleware",
    "django.contrib.auth.middleware.LoginRequiredMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django.middleware.csp.ContentSecurityPolicyMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.template.context_processors.csp",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.core.context_processors.app",
            ],
        },
    },
]

DATABASES = {
    "default": env.db("DATABASE_URL", default="postgres://dianna:dianna@localhost:5434/dianna"),
}
DATABASES["default"]["CONN_MAX_AGE"] = env.int("CONN_MAX_AGE", default=60)
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Hôtes (T-08, T-22) : <BASE_DOMAIN> vitrine, admin.<BASE_DOMAIN> éditeur, <slug>.<BASE_DOMAIN>
BASE_DOMAIN = env("BASE_DOMAIN", default="localhost")
PLATFORM_SUBDOMAIN = "admin"
SITE_SCHEME = env("SITE_SCHEME", default="https")
SITE_PORT = env("SITE_PORT", default="")
DEV_COMPANY_SLUG = env("DEV_COMPANY_SLUG", default="")

# Proxys de confiance devant l'application (répartiteur de l'hébergeur) : l'adresse IP du
# client est lue dans X-Forwarded-For en conséquence (apps.core.http.client_ip, allauth).
TRUSTED_PROXY_COUNT = env.int("TRUSTED_PROXY_COUNT", default=0)
ALLAUTH_TRUSTED_PROXY_COUNT = TRUSTED_PROXY_COUNT

# Comptes (L0-01, T-09, T-10)
AUTH_USER_MODEL = "accounts.User"
AUTHENTICATION_BACKENDS = ["apps.accounts.auth.HostAwareBackend"]
LOGIN_URL = "account_login"
LOGIN_REDIRECT_URL = "/"
ACCOUNT_ADAPTER = "apps.accounts.adapter.AccountAdapter"
ACCOUNT_FORMS = {
    "login": "apps.accounts.adapter.DiannaLoginForm",
    "reset_password": "apps.accounts.adapter.TenantResetPasswordForm",
    "user_token": "apps.accounts.adapter.TenantUserTokenForm",
}
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*"]
ACCOUNT_USER_MODEL_USERNAME_FIELD = None
ACCOUNT_EMAIL_VERIFICATION = "none"
ACCOUNT_SESSION_REMEMBER = True  # pas de case « se souvenir de moi » : session de 12 h
ACCOUNT_LOGOUT_REDIRECT_URL = "account_login"
ACCOUNT_PREVENT_ENUMERATION = True
# Adresse inconnue de l'espace : aucun e-mail (il citerait l'espace à un tiers).
ACCOUNT_EMAIL_UNKNOWN_ACCOUNTS = False
ACCOUNT_EMAIL_SUBJECT_PREFIX = "Dianna : "
ACCOUNT_LOGIN_ON_PASSWORD_RESET = False
MFA_SUPPORTED_TYPES = ["totp", "recovery_codes"]
MFA_TOTP_ISSUER = "Dianna"
MFA_TRUST_ENABLED = False
# Secrets TOTP et codes de secours chiffrés (Fernet). Clé distincte de SECRET_KEY ; plusieurs
# clés séparées par des virgules pour en changer : la première chiffre, toutes déchiffrent.
MFA_ADAPTER = "apps.accounts.mfa.EncryptingMFAAdapter"
MFA_ENCRYPTION_KEY = env("MFA_ENCRYPTION_KEY", default="")
# Arguments chiffrés des tâches qui portent un e-mail d'allauth (A3-04) : clé dédiée,
# distincte de SECRET_KEY et de MFA_ENCRYPTION_KEY.
TASKS_ENCRYPTION_KEY = env("TASKS_ENCRYPTION_KEY", default="")
# Double authentification des comptes de démonstration RH et Admin : développement seulement.
DEMO_DISABLE_2FA = env.bool("DEMO_DISABLE_2FA", default=False)

# Cache : limitation des tentatives (allauth, vitrine). Base de données en production pour
# être partagé entre les processus Gunicorn (`createcachetable` au déploiement).
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 12},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Session : expiration après 12 h d'inactivité (fiche socle)
SESSION_COOKIE_AGE = 12 * 60 * 60
SESSION_SAVE_EVERY_REQUEST = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Lax"

# Langue et dates
LANGUAGE_CODE = "fr"
LANGUAGES = [("fr", "Français")]
TIME_ZONE = "Europe/Paris"
USE_I18N = True
USE_TZ = True
LOCALE_PATHS = [BASE_DIR / "locale"]

# Fichiers statiques : la feuille Tailwind compilée est dans static/build/ (make css-build)
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
# Fichiers privés (photos, logos, justificatifs) : hors des fichiers statiques, servis par
# URL signée après contrôle d'accès (apps.core.files). Stockage objet S3 en production (T-12).
PRIVATE_MEDIA_ROOT = env.path("PRIVATE_MEDIA_ROOT", default=BASE_DIR / "private_media")
PRIVATE_FILE_URL_SECONDS = 5 * 60
# Stockage des fichiers privés (T-12, L5-02) : « filesystem » (développement, tests) ou « s3 »
# (Scaleway Object Storage fr-par en production, MinIO dans l'intégration continue).
PRIVATE_STORAGE_BACKEND = env("PRIVATE_STORAGE_BACKEND", default="filesystem")
S3_BUCKET = env("S3_BUCKET", default="")
S3_ENDPOINT_URL = env("S3_ENDPOINT_URL", default="")
S3_REGION = env("S3_REGION", default="fr-par")
S3_ACCESS_KEY = env("S3_ACCESS_KEY", default="")
S3_SECRET_KEY = env("S3_SECRET_KEY", default="")
S3_SERVER_SIDE_ENCRYPTION = env("S3_SERVER_SIDE_ENCRYPTION", default="")
DATA_UPLOAD_MAX_MEMORY_SIZE = 6 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 6 * 1024 * 1024

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

# Politique de sécurité du contenu, active dès le lot 0. Aucun 'unsafe-inline' ni
# 'unsafe-eval' : pas d'attribut style, pas de hx-on, pas d'eval dans HTMX (L0-02).
SECURE_CSP = {
    "default-src": [CSP.SELF],
    "script-src": [CSP.SELF, CSP.NONCE],
    "style-src": [CSP.SELF],
    "img-src": [CSP.SELF, "data:"],
    "font-src": [CSP.SELF],
    "connect-src": [CSP.SELF],
    "object-src": [CSP.NONE],
    "base-uri": [CSP.SELF],
    "form-action": [CSP.SELF],
    "frame-ancestors": [CSP.NONE],
}
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"

# E-mails : réglage MAILERS de Django 6.1 (EMAIL_BACKEND est déprécié). Le fournisseur
# européen (T-13, django-anymail) sera branché avant la recette.
MAILERS = {
    "default": {
        "BACKEND": env("MAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend"),
    },
}
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="Dianna <ne-pas-repondre@dianna.fr>")

# Messages Django affichés en notifications visuelles (components/toast.html)
MESSAGE_TAGS = {
    messages.DEBUG: "info",
    messages.INFO: "info",
    messages.SUCCESS: "ok",
    messages.WARNING: "warn",
    messages.ERROR: "err",
}

# Tâches en arrière-plan (T-11, L3-01) : travailleur `python manage.py db_worker`.
TASKS = {"default": {"BACKEND": "django_tasks_db.DatabaseBackend"}}

# Annulation immédiate (L0-03) : fenêtre côté serveur et délai des e-mails annulables
UNDO_WINDOW_SECONDS = 30
UNDOABLE_EMAIL_DELAY_SECONDS = 45

# Journaux : jamais de donnée personnelle (règle 5 de CLAUDE.md)
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "plain": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"},
    },
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "plain"}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", default="INFO")},
    "loggers": {
        # Les requêtes refusées contiennent des URL et des en-têtes : niveau ERROR seulement.
        "django.request": {"level": "ERROR", "propagate": True},
        # Exports PDF : la progression de WeasyPrint n'apporte rien au journal.
        "weasyprint": {"level": "WARNING", "propagate": True},
        "fontTools": {"level": "WARNING", "propagate": True},
    },
}
