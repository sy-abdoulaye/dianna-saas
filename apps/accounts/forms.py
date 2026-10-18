from django import forms
from django.contrib.auth.password_validation import validate_password
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import User


class InvitationPasswordForm(forms.Form):
    password1 = forms.CharField(
        label=_("Mot de passe"),
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        help_text=_("12 caractères au minimum."),
    )
    password2 = forms.CharField(
        label=_("Confirmer le mot de passe"),
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )

    def __init__(self, *args, employee=None, **kwargs):
        self.employee = employee
        super().__init__(*args, **kwargs)

    def clean_password1(self):
        password = self.cleaned_data["password1"]
        candidate = User(email=self.employee.email if self.employee else "")
        validate_password(password, candidate)
        return password

    def clean_password2(self):
        password1 = self.cleaned_data.get("password1")
        password2 = self.cleaned_data["password2"]
        if password1 and password1 != password2:
            raise forms.ValidationError(_("Les deux mots de passe ne correspondent pas."))
        return password2
