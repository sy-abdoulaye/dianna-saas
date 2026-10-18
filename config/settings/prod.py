"""Recette et production. Toutes les valeurs sensibles viennent de l'environnement."""

from .base import *  # noqa: F403
from .base import env

DEBUG = False
STYLEGUIDE_ENABLED = False

STORAGES["staticfiles"] = {  # noqa: F405
    "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
}

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=60 * 60 * 24 * 365)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
# Préchargement HSTS : engagement difficile à défaire, décidé avec le nom de domaine (lot 8).
SECURE_HSTS_PRELOAD = False
SILENCED_SYSTEM_CHECKS = ["security.W021"]
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

MAILERS = {
    "default": {
        "BACKEND": env("MAIL_BACKEND", default="django.core.mail.backends.smtp.EmailBackend"),
    },
}
