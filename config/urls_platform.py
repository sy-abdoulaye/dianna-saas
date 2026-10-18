"""Routes de l'administration éditeur (admin.<BASE_DOMAIN>, T-22)."""

from django.contrib import admin
from django.contrib.auth.decorators import login_not_required
from django.contrib.auth.views import redirect_to_login
from django.urls import path

from apps.accounts.urls import auth_patterns


@login_not_required
def admin_login(request, extra_context=None):
    """La connexion passe par allauth (mot de passe puis code TOTP)."""
    return redirect_to_login(request.GET.get("next", "/"))


admin.site.login = admin_login

urlpatterns = [
    *auth_patterns,
    path("", admin.site.urls),
]

handler403 = "apps.core.views.permission_denied"
handler404 = "apps.core.views.page_not_found"
handler500 = "apps.core.views.server_error"
