"""Développement local."""

from .base import *  # noqa: F403
from .base import env

DEBUG = True
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[".localhost", "localhost"])
SITE_SCHEME = "http"
SITE_PORT = env("SITE_PORT", default="8000")
DEMO_DISABLE_2FA = env.bool("DEMO_DISABLE_2FA", default=True)
# Clé de développement, publique : ne jamais la réutiliser ailleurs.
MFA_ENCRYPTION_KEY = env(
    "MFA_ENCRYPTION_KEY", default="WZN2RvTcO7WNrpNnyeuRhaHr1EaPNGYK915NO6vU_xA="
)
STYLEGUIDE_ENABLED = True
WHITENOISE_USE_FINDERS = True
WHITENOISE_AUTOREFRESH = True
TASKS_ENCRYPTION_KEY = env(
    "TASKS_ENCRYPTION_KEY", default="-pfornFqHIfl-pNmlSJCbB4ZnRcI4ITzsfYDXRDCJ9Y="
)
