"""Développement local."""

from .base import *  # noqa: F403
from .base import env

DEBUG = True
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[".localhost", "127.0.0.1"])
STYLEGUIDE_ENABLED = True
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
