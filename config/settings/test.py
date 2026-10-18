"""Tests automatisés (pytest)."""

from .base import *  # noqa: F403

DEBUG = False
ALLOWED_HOSTS = [".localhost", "127.0.0.1", "testserver"]
STYLEGUIDE_ENABLED = True
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
MAILERS = {"default": {"BACKEND": "django.core.mail.backends.locmem.EmailBackend"}}
WHITENOISE_USE_FINDERS = True
WHITENOISE_AUTOREFRESH = True
DATABASES["default"]["CONN_MAX_AGE"] = 0  # noqa: F405
