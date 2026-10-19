"""Routes de la vitrine (<BASE_DOMAIN>, T-08)."""

from django.conf import settings
from django.contrib import admin
from django.urls import include, path

from apps.core import views

urlpatterns = [
    path("", views.public_home, name="public_home"),
]

if settings.DEBUG:
    # Développement uniquement (L0-13) : administration éditeur sur /editeur/ ; en production
    # elle est servie seulement sur admin.<BASE_DOMAIN>.
    import config.urls_platform  # noqa: F401  (connexion de l'administration par allauth)
    from apps.accounts.urls import auth_patterns

    urlpatterns += [*auth_patterns, path("editeur/", admin.site.urls)]

if settings.STYLEGUIDE_ENABLED:
    urlpatterns += [path("dev/", include("apps.core.dev_urls"))]

handler403 = "apps.core.views.permission_denied"
handler404 = "apps.core.views.page_not_found"
handler500 = "apps.core.views.server_error"
