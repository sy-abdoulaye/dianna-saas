"""Développement local."""

from .base import *  # noqa: F403
from .base import env

DEBUG = True
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[".localhost", "localhost"])
SITE_SCHEME = "http"
SITE_PORT = env("SITE_PORT", default="8000")
DEMO_DISABLE_2FA = env.bool("DEMO_DISABLE_2FA", default=True)
STYLEGUIDE_ENABLED = True
WHITENOISE_USE_FINDERS = True
WHITENOISE_AUTOREFRESH = True
