"""Connexion et compte : chemins visibles en français (L1-03), noms de routes d'allauth
conservés (ils sont utilisés par allauth lui-même)."""

from allauth.account import views as account
from allauth.mfa.base import views as mfa
from allauth.mfa.recovery_codes import views as recovery
from allauth.mfa.totp import views as totp
from django.urls import path, re_path

from apps.accounts import views

auth_patterns = [
    path("connexion/", account.login, name="account_login"),
    path("connexion/deconnexion/", account.logout, name="account_logout"),
    path("connexion/inactif/", account.account_inactive, name="account_inactive"),
    path("connexion/inscription/", account.signup, name="account_signup"),
    path("connexion/verification/", account.reauthenticate, name="account_reauthenticate"),
    path("connexion/mot-de-passe/", account.password_reset, name="account_reset_password"),
    path(
        "connexion/mot-de-passe/envoye/",
        account.password_reset_done,
        name="account_reset_password_done",
    ),
    re_path(
        r"^connexion/mot-de-passe/cle/(?P<uidb36>[0-9A-Za-z]+)-(?P<key>.+)/$",
        account.password_reset_from_key,
        name="account_reset_password_from_key",
    ),
    path(
        "connexion/mot-de-passe/modifie/",
        account.password_reset_from_key_done,
        name="account_reset_password_from_key_done",
    ),
    path("compte/mot-de-passe/", account.password_change, name="account_change_password"),
    path("connexion/2fa/", mfa.authenticate, name="mfa_authenticate"),
    path("connexion/2fa/verification/", mfa.reauthenticate, name="mfa_reauthenticate"),
    path("compte/securite/", mfa.index, name="mfa_index"),
    path("compte/securite/totp/activer/", totp.activate_totp, name="mfa_activate_totp"),
    path("compte/securite/totp/desactiver/", totp.deactivate_totp, name="mfa_deactivate_totp"),
    path(
        "compte/securite/codes-de-secours/",
        recovery.view_recovery_codes,
        name="mfa_view_recovery_codes",
    ),
    path(
        "compte/securite/codes-de-secours/generer/",
        recovery.generate_recovery_codes,
        name="mfa_generate_recovery_codes",
    ),
    path(
        "compte/securite/codes-de-secours/telecharger/",
        recovery.download_recovery_codes,
        name="mfa_download_recovery_codes",
    ),
]

app_name = "accounts"

urlpatterns = [
    path("invitation/<str:token>/", views.invitation, name="invitation"),
    path("invitation/<str:token>/renouveler/", views.invitation_renew, name="invitation_renew"),
    path("compte/theme/", views.theme, name="theme"),
]
