"""Développement local."""

from .base import *  # noqa: F403
from .base import env

DEBUG = True
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[".localhost", "127.0.0.1"])
STYLEGUIDE_ENABLED = True
WHITENOISE_USE_FINDERS = True
WHITENOISE_AUTOREFRESH = True
