"""Formulaires des demandes : messages du prototype et de la fiche 05. Ils ne vérifient
que les champs eux-mêmes (date passée, week-end, durée, heures). Les contrôles qui dépendent
des autres demandes (quota, même jour, chevauchements, période de la campagne) sont faits
par le service, sous verrou de la fiche du demandeur : `workflow.check_request` (A3-02)."""

from datetime import timedelta
from decimal import Decimal

from django import forms
from django.utils.translation import gettext_lazy as _

from apps.approvals import rules
from apps.approvals.models import (
    LeaveRequest,
    OnCallDeclaration,
    SummerCampaign,
    TransportProof,
)
from apps.core.dates import format_date
from apps.core.fields import DecimalTextField

DATE = forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")
TEXT = forms.Textarea(attrs={"rows": 3, "placeholder": _("Facultatif")})
MAX_LEAVE_DAYS = 31


class RequestForm(forms.Form):
    def __init__(self, *args, requester=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.requester = requester

    def model_data(self) -> dict:
        raise NotImplementedError


class TeleworkForm(RequestForm):
    date = forms.DateField(
        label=_("Jour"), widget=DATE, error_messages={"required": _("Choisissez un jour.")}
    )
    comment = forms.CharField(label=_("Commentaire"), required=False, widget=TEXT)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        quota = rules.weekly_quota(self.requester)
        self.fields["date"].help_text = _(
            "Du lundi au vendredi. %(n)s jours maximum par semaine."
        ) % {"n": quota}
        self.fields["date"].widget.attrs["min"] = rules.today().isoformat()

    def clean_date(self):
        day = self.cleaned_data["date"]
        if day < rules.today():
            raise forms.ValidationError(
                _("Ce jour est passé. Choisissez une date à partir d'aujourd'hui.")
            )
        if day.weekday() >= 5:
            raise forms.ValidationError(_("Le télétravail se déclare du lundi au vendredi."))
        return day

    def model_data(self):
        return {"date": self.cleaned_data["date"], "comment": self.cleaned_data["comment"]}


class LeaveForm(RequestForm):
    start = forms.DateField(
        label=_("Premier jour"),
        widget=DATE,
        error_messages={"required": _("Choisissez le premier jour.")},
    )
    end = forms.DateField(
        label=_("Dernier jour"),
        widget=DATE,
        error_messages={"required": _("Choisissez le dernier jour.")},
    )
    leave_type = forms.ChoiceField(label=_("Type"), choices=LeaveRequest.LeaveType.choices)
    comment = forms.CharField(label=_("Commentaire"), required=False, widget=TEXT)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.campaign = rules.open_campaign()
        if self.campaign is None:
            self.fields["leave_type"].initial = LeaveRequest.LeaveType.OTHER
        for name in ("start", "end"):
            self.fields[name].widget.attrs["min"] = rules.today().isoformat()

    def clean_start(self):
        start = self.cleaned_data["start"]
        if start < rules.today():
            raise forms.ValidationError(_("La date est passée."))
        return start

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get("start"), cleaned.get("end")
        if not start or not end:
            return cleaned
        if end < start:
            self.add_error("end", _("Le dernier jour doit être après le premier."))
            return cleaned
        if (end - start) + timedelta(days=1) > timedelta(days=MAX_LEAVE_DAYS):
            self.add_error(
                "end", _("Une demande couvre au maximum 31 jours. Faites deux demandes.")
            )
        return cleaned

    def model_data(self):
        return {k: self.cleaned_data[k] for k in ("start", "end", "leave_type", "comment")}


class OnCallForm(RequestForm):
    kind = forms.ChoiceField(label=_("Type"), choices=OnCallDeclaration.Kind.choices)
    start = forms.DateField(
        label=_("Début"),
        widget=DATE,
        error_messages={"required": _("Choisissez la date de début.")},
    )
    end = forms.DateField(
        label=_("Fin"), widget=DATE, error_messages={"required": _("Choisissez la date de fin.")}
    )
    hours = DecimalTextField(
        label=_("Durée d'intervention (heures)"),
        required=False,
        help_text=_("Obligatoire pour une intervention."),
        format_message=_("Saisissez une durée comme 2,5."),
    )
    description = forms.CharField(
        label=_("Description"),
        required=False,
        widget=forms.Textarea(
            attrs={"rows": 3, "placeholder": _("Ex. incident serveur de messagerie")}
        ),
    )

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get("start"), cleaned.get("end")
        if start and end and end < start:
            self.add_error("end", _("La fin doit être après le début."))
        hours = cleaned.get("hours")
        if cleaned.get("kind") == OnCallDeclaration.Kind.INTERVENTION and (
            hours is None or hours <= 0
        ):
            self.add_error("hours", _("Indiquez la durée de l'intervention."))
        if hours is not None:
            if hours > 24:
                self.add_error(
                    "hours", _("Une intervention dure au plus 24 heures par déclaration.")
                )
            elif hours % Decimal("0.5"):
                self.add_error("hours", _("Indiquez une durée par demi-heure."))
        return cleaned

    def model_data(self):
        data = {k: self.cleaned_data[k] for k in ("kind", "start", "end", "hours", "description")}
        if data["kind"] == OnCallDeclaration.Kind.ON_CALL:
            data["hours"] = None
        return data


class ReasonForm(forms.Form):
    reason = forms.CharField(
        label=_("Motif"),
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text=_("Le motif est transmis au salarié."),
        error_messages={"required": _("Indiquez le motif.")},
    )

    def __init__(self, *args, label=None, required_message=None, **kwargs):
        super().__init__(*args, **kwargs)
        if label:
            self.fields["reason"].label = label
        if required_message:
            self.fields["reason"].error_messages["required"] = required_message


class CampaignForm(forms.ModelForm):
    class Meta:
        model = SummerCampaign
        fields = ["label", "period_start", "period_end", "deadline", "conflict_threshold"]
        widgets = {"period_start": DATE, "period_end": DATE, "deadline": DATE}
        labels = {"conflict_threshold": _("Seuil d'alerte de conflit (%)")}
        help_texts = {
            "conflict_threshold": _(
                "Alerte renforcée quand plus de ce pourcentage du service est absent le même jour."
            )
        }

    def clean(self):
        cleaned = super().clean()
        start, end, deadline = (
            cleaned.get("period_start"),
            cleaned.get("period_end"),
            cleaned.get("deadline"),
        )
        if start and end and end < start:
            self.add_error("period_end", _("La fin doit être après le début."))
        if deadline and start and deadline > start:
            self.add_error("deadline", _("La date limite doit précéder la période."))
        return cleaned


EXPORT_FORMATS = [("csv", _("CSV (tableur)")), ("xlsx", _("Excel"))]


class MonthExportForm(forms.Form):
    """Exports RH mensuels (télétravail, astreintes) : mois et format."""

    mois = forms.DateField(
        label=_("Mois"),
        input_formats=["%Y-%m"],
        widget=forms.DateInput(attrs={"type": "month"}, format="%Y-%m"),
        error_messages={"required": _("Choisissez le mois."), "invalid": _("Choisissez le mois.")},
    )
    format = forms.ChoiceField(
        label=_("Format"), choices=EXPORT_FORMATS, initial="csv", widget=forms.RadioSelect
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["mois"].initial = rules.today().replace(day=1)

    def clean_mois(self):
        from apps.planning.services import in_bounds

        month = self.cleaned_data["mois"]
        if not in_bounds(month):
            raise forms.ValidationError(_("Choisissez une date entre 2000 et 2100."))
        return month


class CampaignExportForm(forms.Form):
    campagne = forms.ChoiceField(label=_("Campagne"))
    format = forms.ChoiceField(
        label=_("Format"), choices=EXPORT_FORMATS, initial="csv", widget=forms.RadioSelect
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.campaigns = {str(c.pk): c for c in SummerCampaign.objects.order_by("-period_start")}
        self.fields["campagne"].choices = [(pk, c.label) for pk, c in self.campaigns.items()]
        opened = next((pk for pk, c in self.campaigns.items() if c.status == "open"), None)
        self.fields["campagne"].initial = opened

    def clean_campagne(self):
        return self.campaigns[self.cleaned_data["campagne"]]


class TransportForm(RequestForm):
    """Justificatif de transport (fiche 05, section Transport). Les contrôles qui dépendent
    des autres justificatifs (chevauchement) sont faits par le service (A3-02)."""

    month = forms.DateField(
        label=_("Mois concerné"),
        input_formats=["%Y-%m"],
        widget=forms.DateInput(attrs={"type": "month"}, format="%Y-%m"),
        error_messages={"required": _("Choisissez le mois."), "invalid": _("Choisissez le mois.")},
    )
    ticket_type = forms.ChoiceField(
        label=_("Type de titre"), choices=TransportProof.TicketType.choices
    )
    amount = DecimalTextField(
        label=_("Montant payé (€)"),
        format_message=_("Saisissez un montant comme 84,10."),
        error_messages={"required": _("Indiquez un montant supérieur à 0.")},
    )
    file = forms.FileField(
        label=_("Justificatif (PDF, JPG ou PNG)"),
        widget=forms.ClearableFileInput(attrs={"accept": ".pdf,image/png,image/jpeg"}),
        error_messages={"required": _("Joignez le justificatif.")},
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["month"].initial = rules.today().replace(day=1)

    def clean_month(self):
        month = self.cleaned_data["month"].replace(day=1)
        first, last = transport_months()
        if not first <= month <= last:
            raise forms.ValidationError(
                _("Choisissez un mois entre %(a)s et %(b)s.")
                % {"a": format_date(first, "month"), "b": format_date(last, "month")}
            )
        return month

    def clean_amount(self):
        amount = self.cleaned_data["amount"]
        if amount <= 0:
            raise forms.ValidationError(_("Indiquez un montant supérieur à 0."))
        if amount > 1000:
            raise forms.ValidationError(_("Le montant semble trop élevé. Vérifiez la saisie."))
        return amount

    def clean_file(self):
        from django.core.exceptions import ValidationError

        from apps.core.files import DOCUMENT_TYPES, clean_document

        uploaded = self.cleaned_data["file"]
        try:
            content, extension = clean_document(uploaded)
        except ValidationError as error:
            raise forms.ValidationError(error.messages[0]) from error
        self.document = (content, extension, DOCUMENT_TYPES[extension], uploaded.name)
        return uploaded

    def model_data(self):
        content, extension, mime, original = self.document
        content.name = f"justificatif.{extension}"
        return {
            "month": self.cleaned_data["month"],
            "ticket_type": self.cleaned_data["ticket_type"],
            "amount": self.cleaned_data["amount"],
            "file": content,
            "file_type": mime,
            "original_name": safe_filename(original, extension),
        }


def transport_months():
    """Mois acceptés : des 12 mois passés au mois prochain (L5-07)."""
    current = rules.today().replace(day=1)
    year, month = divmod(current.month - 1 - 12, 12)
    first = current.replace(year=current.year + year, month=month + 1)
    year, month = divmod(current.month, 12)
    last = current.replace(year=current.year + year, month=month + 1)
    return first, last


def safe_filename(name: str, extension: str) -> str:
    """Nom d'origine affiché et proposé au téléchargement (jamais utilisé pour le stockage) :
    sans chemin ni caractère de contrôle, 120 caractères au plus, avec la bonne extension."""
    import re

    base = re.split(r"[\\/]", name or "")[-1]
    base = re.sub(r"[\x00-\x1f\x7f]", "", base).strip().rsplit(".", 1)[0][:100]
    return f"{base or 'justificatif'}.{extension}"


FORMS = {
    "telework": TeleworkForm,
    "leave": LeaveForm,
    "on_call": OnCallForm,
    "transport": TransportForm,
}


STATUS_FILTER_CHOICES = [
    ("", _("Tous")),
    ("pending", _("En attente")),
    ("approved", _("Validées")),
    ("refused", _("Refusées")),
    ("cancelled", _("Annulées")),
]


class RequestFilterForm(forms.Form):
    """Filtres de la page d'un type de demande. « Mes demandes » : recherche dans le résumé ;
    autres onglets : nom du collaborateur."""

    onglet = forms.CharField(required=False, widget=forms.HiddenInput)
    q = forms.CharField(
        label=_("Recherche"),
        required=False,
        widget=forms.TextInput(attrs={"type": "search", "id": "request-q"}),
    )
    statut = forms.ChoiceField(
        label=_("Statut"),
        required=False,
        choices=STATUS_FILTER_CHOICES,
        widget=forms.Select(attrs={"id": "request-status"}),
    )

    def __init__(self, data, *, tab: str, mine: bool):
        data = data.copy()
        data["onglet"] = tab
        super().__init__(data)
        self.fields["q"].widget.attrs["placeholder"] = (
            _("Rechercher dans mes demandes") if mine else _("Nom du collaborateur")
        )
