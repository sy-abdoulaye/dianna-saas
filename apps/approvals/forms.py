"""Formulaires des demandes : messages du prototype et de la fiche 05. Ils ne vérifient
que les champs eux-mêmes (date passée, week-end, durée, heures). Les contrôles qui dépendent
des autres demandes (quota, même jour, chevauchements, période de la campagne) sont faits
par le service, sous verrou de la fiche du demandeur : `workflow.check_request` (A3-02)."""

from datetime import timedelta
from decimal import Decimal

from django import forms
from django.utils.translation import gettext_lazy as _

from apps.approvals import rules
from apps.approvals.models import LeaveRequest, OnCallDeclaration, SummerCampaign

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
    hours = forms.DecimalField(
        label=_("Durée d'intervention (heures)"),
        required=False,
        max_digits=4,
        decimal_places=1,
        help_text=_("Obligatoire pour une intervention."),
        widget=forms.NumberInput(attrs={"step": "0.5", "min": "0.5", "max": "24"}),
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


FORMS = {"telework": TeleworkForm, "leave": LeaveForm, "on_call": OnCallForm}
