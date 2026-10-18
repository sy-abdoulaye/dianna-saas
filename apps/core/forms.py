from django import forms
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import User, normalize_email
from apps.people.models import Employee


class SpaceAccessForm(forms.Form):
    email = forms.EmailField(
        label=_("Adresse e-mail professionnelle"),
        widget=forms.EmailInput(attrs={"autocomplete": "email"}),
    )

    UNKNOWN = _(
        "Aucun espace n'est associé à cette adresse. Vérifiez la saisie ou contactez votre "
        "service RH."
    )

    def clean_email(self):
        email = normalize_email(self.cleaned_data["email"])
        user = User.objects.filter(email=email, is_active=True).first()
        employee = (
            Employee.all_companies.select_related("company").filter(user=user).first()
            if user
            else None
        )
        if employee is None or not employee.company.is_active:
            raise forms.ValidationError(self.UNKNOWN)
        self.company = employee.company
        return email
