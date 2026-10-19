"""Double authentification obligatoire (T-10) : RH et administrateurs sur l'espace de leur
entreprise, équipe Dianna sur l'hôte éditeur. Sans authentificateur TOTP enregistré, la
personne est redirigée vers l'inscription, quelle que soit la page demandée : à la première
connexion, et dès que son profil passe à RH ou Administrateur.
"""

from allauth.mfa.models import Authenticator
from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect
from django.utils.translation import gettext as _

from apps.core.middleware import PLATFORM, PUBLIC, TENANT

ALLOWED_URL_NAMES = frozenset(
    {
        "mfa_activate_totp",
        "mfa_view_recovery_codes",
        "mfa_generate_recovery_codes",
        "mfa_download_recovery_codes",
        "mfa_index",
        "account_logout",
        "account_reauthenticate",
        "mfa_reauthenticate",
    }
)


def two_factor_required(request) -> bool:
    if settings.DEBUG and getattr(settings, "DEMO_DISABLE_2FA", False):
        return False
    user = request.user
    kind = getattr(request, "host_kind", None)
    if kind == TENANT:
        return request.employee is not None and request.employee.requires_two_factor
    if kind in (PLATFORM, PUBLIC):
        return user.is_staff
    return False


def has_totp(user) -> bool:
    return Authenticator.objects.filter(user=user, type=Authenticator.Type.TOTP).exists()


class TwoFactorEnrollmentMiddleware:
    """S'exécute après la résolution de l'URL (process_view) : les routes de l'hôte courant
    sont alors actives pour la redirection."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        user = getattr(request, "user", None)
        if not (user is not None and user.is_authenticated and two_factor_required(request)):
            return None
        match = request.resolver_match
        if match is not None and match.url_name in ALLOWED_URL_NAMES:
            return None
        if has_totp(user):
            return None
        messages.info(request, _("Activez la double authentification pour continuer."))
        return redirect("mfa_activate_totp")
