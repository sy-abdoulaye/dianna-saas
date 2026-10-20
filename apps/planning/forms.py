"""Formulaires du planning (docs/modules/06-planning.md)."""

from datetime import timedelta

from django import forms
from django.utils.translation import gettext_lazy as _

from apps.core import permissions
from apps.core.models import Service
from apps.planning import services

DATE = forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")
PERIODS = [
    ("semaine", _("Semaine en cours")),
    ("semaine-prochaine", _("Semaine prochaine")),
    ("mois", _("Mois en cours")),
    ("personnalisee", _("Période personnalisée")),
]
FORMATS = [
    ("csv", _("CSV (tableur)")),
    ("xlsx", _("Excel")),
    ("ics", _("iCalendar (agenda)")),
    ("pdf", _("PDF")),
]
FORMAT_LABELS = {"csv": "CSV", "xlsx": "Excel", "ics": "iCalendar", "pdf": "PDF"}


class ExportForm(forms.Form):
    periode = forms.ChoiceField(label=_("Période"), choices=PERIODS, initial="semaine")
    perimetre = forms.ChoiceField(label=_("Périmètre"), required=False)
    debut = forms.DateField(label=_("Du (période personnalisée)"), required=False, widget=DATE)
    fin = forms.DateField(label=_("Au (période personnalisée)"), required=False, widget=DATE)
    format = forms.ChoiceField(
        label=_("Format"), choices=FORMATS, initial="csv", widget=forms.RadioSelect
    )

    def __init__(self, *args, viewer, today, **kwargs):
        super().__init__(*args, **kwargs)
        self.viewer, self.today = viewer, today
        self.company_wide = permissions.scope(viewer, "planning.export") == permissions.ALL
        if self.company_wide:
            self.services = {str(s.pk): s for s in Service.objects.order_by("name")}
            choices = [("", _("Toute l'entreprise"))] + [
                (pk, s.name) for pk, s in self.services.items()
            ]
        else:
            self.services = {}
            own = viewer.service.name if viewer.service_id else _("mon équipe")
            choices = [("", _("Service %(name)s") % {"name": own})]
        self.fields["perimetre"].choices = choices
        self.fields["debut"].initial = today
        self.fields["fin"].initial = today + timedelta(days=13)

    def clean_perimetre(self):
        # Hors RH et administrateur : toujours le périmètre de la personne (jamais un autre
        # service, même en modifiant le formulaire).
        return self.services.get(self.cleaned_data.get("perimetre") or "")

    def clean(self):
        cleaned = super().clean()
        period = cleaned.get("periode")
        today = self.today
        if period == "semaine":
            first, last = services.week_of(today)
        elif period == "semaine-prochaine":
            first, last = services.week_of(today + timedelta(days=7))
        elif period == "mois":
            first, last = services.month_of(today)
        else:
            first, last = cleaned.get("debut"), cleaned.get("fin")
            if not first:
                self.add_error("debut", _("Choisissez la date de début."))
            if not last:
                self.add_error("fin", _("Choisissez la date de fin."))
            if first and last and last < first:
                self.add_error("fin", _("La fin doit être après le début."))
            elif first and last and (last - first).days + 1 > services.MAX_EXPORT_DAYS:
                self.add_error("fin", _("La période est limitée à 3 mois par export."))
        cleaned["first"], cleaned["last"] = first, last
        return cleaned

    @property
    def scope_label(self) -> str:
        service = self.cleaned_data.get("perimetre")
        if service is not None:
            return _("service %(name)s") % {"name": service.name}
        if self.company_wide:
            return _("toute l'entreprise")
        return _("mon périmètre")
