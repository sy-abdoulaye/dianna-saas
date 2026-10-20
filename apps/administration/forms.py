from datetime import timedelta

from django import forms
from django.db.models.functions import Lower
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.files import clean_image
from apps.core.models import Company
from apps.people.models import Role

LOGO_MAX_BYTES = 1024 * 1024


class CompanyForm(forms.ModelForm):
    logo_upload = forms.FileField(
        label=_("Logo"),
        required=False,
        help_text=_("PNG ou JPG, 1 Mo maximum. Affiché sur la page de connexion."),
        widget=forms.ClearableFileInput(attrs={"accept": "image/png,image/jpeg"}),
    )

    class Meta:
        model = Company
        fields = ["name", "telework_max_per_week", "telework_auto_approve", "summer_leave_hr_step"]
        labels = {
            "name": _("Nom de l'entreprise"),
            "telework_max_per_week": _("Jours de télétravail par semaine"),
            "telework_auto_approve": _(
                "Valider automatiquement le télétravail dans la limite du quota"
            ),
            "summer_leave_hr_step": _("Validation finale des congés d'été par les RH"),
        }
        help_texts = {
            "telework_max_per_week": _("Entre 0 et 5. Appliqué aux nouvelles demandes."),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["name"].error_messages["required"] = _("Indiquez le nom de l'entreprise.")
        quota = self.fields["telework_max_per_week"]
        quota.widget.attrs.update({"min": 0, "max": 5})
        message = _("Saisissez un nombre entier entre 0 et 5.")
        for key in ("required", "invalid", "max_value", "min_value"):
            quota.error_messages[key] = message
        quota.validators = []

    def clean_telework_max_per_week(self):
        value = self.cleaned_data["telework_max_per_week"]
        if value is None or not 0 <= value <= 5:
            raise forms.ValidationError(_("Saisissez un nombre entier entre 0 et 5."))
        return value

    def clean_logo_upload(self):
        upload = self.cleaned_data.get("logo_upload")
        if not upload:
            return None
        return clean_image(upload, max_bytes=LOGO_MAX_BYTES, max_side=400)


class StructureForm(forms.Form):
    """Service ou site : nom unique dans l'entreprise, sans tenir compte de la casse."""

    name = forms.CharField(label=_("Nom"), max_length=80)
    alsace_moselle = forms.BooleanField(
        label=_("Jours fériés d'Alsace-Moselle"),
        required=False,
        help_text=_("Vendredi saint et 26 décembre fériés pour les personnes de ce site."),
    )

    def __init__(self, *args, model=None, instance=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.model = model
        self.instance = instance
        self.fields["name"].error_messages["required"] = _("Indiquez un nom.")
        if not hasattr(model, "alsace_moselle"):
            del self.fields["alsace_moselle"]

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        others = self.model.objects.annotate(n=Lower("name")).filter(n=name.lower())
        if self.instance is not None:
            others = others.exclude(pk=self.instance.pk)
        if others.exists():
            raise forms.ValidationError(_("Ce nom existe déjà."))
        return name


class UsersFilterForm(forms.Form):
    q = forms.CharField(
        label=_("Recherche"),
        required=False,
        widget=forms.TextInput(attrs={"type": "search", "placeholder": _("Nom ou e-mail")}),
    )
    profil = forms.ChoiceField(
        label=_("Profil"), required=False, choices=[("", _("Tous")), *Role.choices]
    )


class JournalFilterForm(forms.Form):
    q = forms.CharField(
        label=_("Recherche"),
        required=False,
        widget=forms.TextInput(attrs={"type": "search", "placeholder": _("Personne ou action")}),
    )
    du = forms.DateField(
        label=_("Du"), required=False, widget=forms.DateInput(attrs={"type": "date"})
    )
    au = forms.DateField(
        label=_("Au"), required=False, widget=forms.DateInput(attrs={"type": "date"})
    )

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get("du"), cleaned.get("au")
        if start and end and end < start:
            self.add_error("au", _("La fin doit être après le début."))
        return cleaned

    def period(self):
        data = getattr(self, "cleaned_data", {}) or {}
        end = data.get("au") or timezone.localdate()
        start = data.get("du") or end - timedelta(days=30)
        return start, end


class ClosureForm(forms.Form):
    """Fermeture d'un jour : toute l'entreprise ou un site (T-16)."""

    date = forms.DateField(
        label=_("Date"),
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        error_messages={"required": _("Choisissez la date.")},
    )
    label = forms.CharField(
        label=_("Libellé"),
        max_length=80,
        widget=forms.TextInput(attrs={"placeholder": _("Ex. pont de l'Ascension")}),
        error_messages={"required": _("Indiquez un libellé.")},
    )
    site = forms.ChoiceField(label=_("Périmètre"), required=False)

    def __init__(self, *args, **kwargs):
        from apps.core.models import Site

        super().__init__(*args, **kwargs)
        self.sites = {str(site.pk): site for site in Site.objects.order_by("name")}
        self.fields["site"].choices = [("", _("Toute l'entreprise"))] + [
            (pk, _("Site de %(name)s") % {"name": site.name}) for pk, site in self.sites.items()
        ]

    def clean_date(self):
        from django.utils import timezone

        day = self.cleaned_data["date"]
        if day < timezone.localdate():
            raise forms.ValidationError(_("La date est passée."))
        return day

    def clean_site(self):
        return self.sites.get(self.cleaned_data.get("site") or "")

    def clean(self):
        from apps.agenda.models import Closure

        cleaned = super().clean()
        day, site = cleaned.get("date"), cleaned.get("site")
        if day and Closure.objects.filter(date=day, site=site).exists():
            self.add_error("date", _("Une fermeture existe déjà ce jour-là pour ce périmètre."))
        return cleaned
