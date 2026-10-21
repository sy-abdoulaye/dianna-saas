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
SITE_SCHEME = "https"
# Obligatoire en production (pas de valeur par défaut) : voir .env.example.
MFA_ENCRYPTION_KEY = env("MFA_ENCRYPTION_KEY")
TASKS_ENCRYPTION_KEY = env("TASKS_ENCRYPTION_KEY")
# Fichiers privés sur S3 (Scaleway Object Storage fr-par, L5-02) ; vérifié par
# `manage.py check --deploy` (dianna.E009).
PRIVATE_STORAGE_BACKEND = env("PRIVATE_STORAGE_BACKEND", default="s3")
S3_SERVER_SIDE_ENCRYPTION = env("S3_SERVER_SIDE_ENCRYPTION", default="AES256")

# Cookies préfixés __Host- : sans Domain, Path=/ et Secure (point 5g de l'audit du lot 1).
SESSION_COOKIE_NAME = "__Host-sessionid"
CSRF_COOKIE_NAME = "__Host-csrftoken"
SESSION_COOKIE_DOMAIN = None
CSRF_COOKIE_DOMAIN = None
SESSION_COOKIE_PATH = "/"
CSRF_COOKIE_PATH = "/"
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "dianna_cache",
    }
}

MAILERS = {
    "default": {
        "BACKEND": env("MAIL_BACKEND", default="django.core.mail.backends.smtp.EmailBackend"),
    },
}
