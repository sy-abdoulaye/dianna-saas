from django.conf import settings
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("editeur/", admin.site.urls),
    path("", include("apps.core.urls")),
]

# Guide de style : jamais monté en production (STYLEGUIDE_ENABLED = False dans prod.py) ;
# la vue renvoie aussi 404 si DEBUG est faux.
if settings.STYLEGUIDE_ENABLED:
    urlpatterns += [path("dev/", include("apps.core.dev_urls"))]

handler403 = "apps.core.views.permission_denied"
handler404 = "apps.core.views.page_not_found"
handler500 = "apps.core.views.server_error"
