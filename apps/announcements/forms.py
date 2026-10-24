"""Formulaires des annonces. Les contrôles de longueur sont refaits par le service."""

from django import forms
from django.utils.translation import gettext_lazy as _

from apps.announcements.models import BODY_MAX, BODY_MIN, TITLE_MAX, Announcement
from apps.announcements.services import AnnouncementData


class AnnouncementForm(forms.Form):
    title = forms.CharField(
        label=_("Titre"),
        max_length=TITLE_MAX,
        error_messages={"required": _("Le titre est obligatoire.")},
    )
    category = forms.ChoiceField(label=_("Catégorie"), choices=Announcement.Category.choices)
    body = forms.CharField(
        label=_("Message"),
        widget=forms.Textarea(attrs={"rows": 6}),
        min_length=BODY_MIN,
        max_length=BODY_MAX,
        help_text=_("Texte simple. Les liens sont détectés automatiquement."),
        error_messages={
            "required": _("Le message est obligatoire."),
            "min_length": _("Le message est trop court (15 caractères minimum)."),
            "max_length": _("Le message dépasse 5 000 caractères."),
        },
    )
    pinned = forms.BooleanField(label=_("Épingler en haut de la liste"), required=False)

    def announcement_data(self) -> AnnouncementData:
        return AnnouncementData(**self.cleaned_data)


class FilterForm(forms.Form):
    q = forms.CharField(
        label=_("Recherche"),
        required=False,
        widget=forms.TextInput(
            attrs={"type": "search", "placeholder": _("Rechercher une annonce")}
        ),
    )
    categorie = forms.ChoiceField(
        label=_("Catégorie"),
        required=False,
        choices=[("", _("Toutes")), *Announcement.Category.choices],
    )
