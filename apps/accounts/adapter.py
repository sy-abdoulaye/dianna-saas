from allauth.account.adapter import DefaultAccountAdapter
from allauth.account.forms import LoginForm, ResetPasswordForm, UserTokenForm
from allauth.core import context
from django.utils.translation import gettext_lazy as _

from apps.accounts.auth import user_can_use_host


class AccountAdapter(DefaultAccountAdapter):
    SILENT_MESSAGES = frozenset(
        {"account/messages/logged_in.txt", "account/messages/logged_out.txt"}
    )

    def is_open_for_signup(self, request):
        """Pas d'inscription libre : les comptes naissent d'une invitation."""
        return False

    def add_message(self, request, level, message_template=None, *args, **kwargs):
        # Connexion et déconnexion : pas de notification visuelle (comme le prototype).
        if message_template in self.SILENT_MESSAGES:
            return
        super().add_message(request, level, message_template, *args, **kwargs)


class TenantResetPasswordForm(ResetPasswordForm):
    """Ne propose la réinitialisation qu'aux comptes qui peuvent se connecter sur cet hôte.
    La réponse est identique dans tous les cas (pas d'énumération des comptes)."""

    def clean_email(self):
        email = super().clean_email()
        self.users = [u for u in self.users if user_can_use_host(u, context.request)]
        return email


class DiannaLoginForm(LoginForm):
    """Libellés du design system, sans texte indicatif dans les champs."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["login"].label = _("E-mail")
        self.fields["password"].label = _("Mot de passe")
        for field in self.fields.values():
            field.widget.attrs.pop("placeholder", None)
        self.fields["login"].widget.attrs["autocomplete"] = "email"
        # allauth place un lien « Mot de passe oublié » dans l'aide : il est déjà sous le bouton.
        self.fields["password"].help_text = ""


class TenantUserTokenForm(UserTokenForm):
    """Clé de réinitialisation : acceptée seulement sur l'hôte où le compte peut se connecter
    (espace de son entreprise, ou hôte éditeur pour l'équipe Dianna). Ailleurs, la clé est
    traitée comme invalide."""

    def _get_user(self, uidb36):
        user = super()._get_user(uidb36)
        if user is not None and not user_can_use_host(user, context.request):
            return None
        return user
