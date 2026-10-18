"""Formulaires de démonstration du guide de style (développement uniquement)."""

from django import forms
from django.utils.translation import gettext_lazy as _

SERVICES = [
    "Support client",
    "Produit et technique",
    "Finance",
    "Moyens généraux",
    "Ressources humaines",
    "Ventes",
]
SITES = ["Lyon", "Paris", "Nantes"]


class DemoRequestForm(forms.Form):
    """Reprend la modale « Déclarer du télétravail » du prototype."""

    day = forms.DateField(label=_("Jour"), widget=forms.DateInput(attrs={"type": "date"}))
    comment = forms.CharField(
        label=_("Commentaire"),
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text=_("Facultatif. Visible par votre manager."),
    )

    def clean_day(self):
        day = self.cleaned_data["day"]
        if day.weekday() >= 5:
            raise forms.ValidationError(_("Le télétravail se déclare du lundi au vendredi."))
        return day


class DemoFieldsForm(forms.Form):
    """Tous les types de champs, pour montrer les états normal et en erreur."""

    first_name = forms.CharField(label=_("Prénom"), max_length=60)
    email = forms.EmailField(
        label=_("E-mail professionnel"), help_text=_("Utilisé pour se connecter à Dianna.")
    )
    service = forms.ChoiceField(
        label=_("Service"), choices=[("", _("Choisir un service"))] + [(s, s) for s in SERVICES]
    )
    note = forms.CharField(label=_("Note"), widget=forms.Textarea(attrs={"rows": 3}), min_length=8)
    pinned = forms.BooleanField(label=_("Épingler en haut de la liste"), required=False)
    proof = forms.FileField(label=_("Justificatif"))
    score = forms.ChoiceField(
        label=_("L'intégration m'a permis de prendre mon poste sereinement"),
        choices=[(str(i), str(i)) for i in range(1, 6)],
        widget=forms.RadioSelect,
        help_text=_("1 = pas du tout d'accord · 5 = tout à fait d'accord"),
    )


class DemoFilterForm(forms.Form):
    q = forms.CharField(
        label=_("Recherche"),
        required=False,
        widget=forms.TextInput(
            attrs={"type": "search", "placeholder": _("Nom, poste, service, e-mail")}
        ),
    )
    service = forms.ChoiceField(
        label=_("Service"),
        required=False,
        choices=[("", _("Tous les services"))] + [(s, s) for s in SERVICES],
    )
    site = forms.ChoiceField(
        label=_("Site"),
        required=False,
        choices=[("", _("Tous les sites"))] + [(s, s) for s in SITES],
    )
