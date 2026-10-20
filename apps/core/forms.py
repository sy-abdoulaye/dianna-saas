import hashlib
import hmac

from django import forms
from django.conf import settings
from django.template.loader import render_to_string
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import User, normalize_email
from apps.core.hosts import company_url
from apps.core.mail import queue_email
from apps.people.models import Employee


class SpaceAccessForm(forms.Form):
    email = forms.EmailField(
        label=_("Adresse e-mail professionnelle"),
        widget=forms.EmailInput(attrs={"autocomplete": "email"}),
    )

    def clean_email(self):
        return normalize_email(self.cleaned_data["email"])


def email_digest(email: str) -> str:
    """Empreinte de l'adresse pour la limitation des tentatives : l'adresse n'est pas stockée
    en clair dans le cache."""
    key = settings.SECRET_KEY.encode()
    return hmac.new(key, normalize_email(email).encode(), hashlib.sha256).hexdigest()


def space_for(email: str):
    """Fiche active associée à l'identifiant de connexion, ou None."""
    user = User.objects.filter(email=normalize_email(email), is_active=True).first()
    if user is None:
        return None
    employee = Employee.all_companies.select_related("company").filter(user=user).first()
    if employee is None or not employee.company.is_active or not employee.can_sign_in:
        return None
    return employee


def send_space_link(email: str, request=None) -> bool:
    """Envoie le lien de connexion à l'espace de l'entreprise, si un compte existe.
    Ne renvoie rien d'exploitable à l'écran : l'appelant affiche toujours le même message."""
    employee = space_for(email)
    if employee is None:
        return False
    context = {
        "employee": employee,
        "company": employee.company,
        "url": company_url(employee.company, "/connexion/", request),
    }
    subject = render_to_string("public/email/space_link_subject.txt", context).strip()
    body = render_to_string("public/email/space_link_message.txt", context)
    queue_email(subject, body, [employee.user.email])
    return True
