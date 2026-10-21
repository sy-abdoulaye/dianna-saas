"""Routes de l'espace d'une entreprise (<slug>.<BASE_DOMAIN>). Voir apps.core.middleware."""

from django.conf import settings
from django.urls import include, path

from apps.accounts.urls import auth_patterns

urlpatterns = [
    *auth_patterns,
    path("", include("apps.accounts.urls")),
    path("", include("apps.core.urls")),
    path("", include("apps.dashboard.urls")),
    path("", include("apps.people.urls")),
    path("", include("apps.administration.urls")),
    path("", include("apps.equipment.urls")),  # avant les demandes : /materiel/
    path("", include("apps.approvals.urls")),
    path("", include("apps.planning.urls")),
]

# Guide de style : jamais monté en production (STYLEGUIDE_ENABLED = False dans prod.py) ;
# la vue renvoie aussi 404 si DEBUG est faux.
if settings.STYLEGUIDE_ENABLED:
    urlpatterns += [path("dev/", include("apps.core.dev_urls"))]

handler403 = "apps.core.views.permission_denied"
handler404 = "apps.core.views.page_not_found"
handler500 = "apps.core.views.server_error"
