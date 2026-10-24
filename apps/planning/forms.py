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
OUT_OF_BOUNDS = _("Choisissez une date entre 2000 et 2100.")
# Périodes prédéfinies de l'export : jour → (début, fin).
PRESET_PERIODS = {
    "semaine": services.week_of,
    "semaine-prochaine": lambda today: services.week_of(today + timedelta(days=7)),
    "mois": services.month_of,
}
PDF_TOO_BIG = _("Pour plus de personnes ou une période plus longue, utilisez l'export Excel.")
FORMAT_LABELS = {"csv": "CSV", "xlsx": "Excel", "ics": "iCalendar", "pdf": "PDF"}


class ExportForm(forms.Form):
    periode = forms.ChoiceField(label=_("Période"), choices=PERIODS, initial="semaine")
    perimetre = forms.ChoiceField(label=_("Périmètre"), required=False)
    debut = forms.DateField(label=_("Du (période personnalisée)"), required=False, widget=DATE)
    fin = forms.DateField(label=_("Au (période personnalisée)"), required=False, widget=DATE)
    format = forms.ChoiceField(
        label=_("Format"), choices=FORMATS, initial="csv", widget=forms.RadioSelect
    )
    # Page du planning affichée (bouton « Exporter » du planning) : le PDF s'y limite (L4-17).
    page = forms.IntegerField(required=False, min_value=1, widget=forms.HiddenInput)

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
        if period in PRESET_PERIODS:
            first, last = PRESET_PERIODS[period](self.today)
        else:
            first, last = self._custom_period(cleaned.get("debut"), cleaned.get("fin"))
        cleaned["first"], cleaned["last"] = first, last
        cleaned["people"] = None
        if cleaned.get("format") == "pdf" and first and last and not self.errors:
            self._limit_pdf(cleaned, first, last)
        return cleaned

    def _custom_period(self, first, last):
        """Période personnalisée : dates dans les bornes, fin après le début, 3 mois au plus.
        Renvoie (début, fin), ou (None, None) avec les erreurs sur les champs."""
        for name, day in (("debut", first), ("fin", last)):
            if day is not None and not services.in_bounds(day):
                self.add_error(name, OUT_OF_BOUNDS)
                first = last = None
        if not first and "debut" not in self.errors:
            self.add_error("debut", _("Choisissez la date de début."))
        if not last and "fin" not in self.errors:
            self.add_error("fin", _("Choisissez la date de fin."))
        if first and last and last < first:
            self.add_error("fin", _("La fin doit être après le début."))
        elif first and last and (last - first).days + 1 > services.MAX_EXPORT_DAYS:
            self.add_error("fin", _("La période est limitée à 3 mois par export."))
        return first, last

    def _limit_pdf(self, cleaned, first, last):
        """PDF : un mois et une page du planning (50 personnes) au plus ; au-delà, l'export
        Excel (L4-17). Avec `page`, le PDF reprend la page affichée du planning."""
        people = services.export_people(self.viewer, service=cleaned.get("perimetre"))
        page = cleaned.get("page")
        if page:
            start = (page - 1) * services.MAX_PDF_PEOPLE
            people = list(people[start : start + services.MAX_PDF_PEOPLE])
        else:
            people = list(people[: services.MAX_PDF_PEOPLE + 1])
        too_long = (last - first).days + 1 > services.MAX_PDF_DAYS
        if too_long or len(people) > services.MAX_PDF_PEOPLE or not people:
            self.add_error("format", PDF_TOO_BIG)
            return
        cleaned["people"] = people

    @property
    def scope_label(self) -> str:
        service = self.cleaned_data.get("perimetre")
        if service is not None:
            return _("service %(name)s") % {"name": service.name}
        if self.company_wide:
            return _("toute l'entreprise")
        return _("mon périmètre")


class PlanningFilterForm(forms.Form):
    """Filtres de la grille : vue, recherche, service (périmètre entreprise), site."""

    vue = forms.ChoiceField(
        label=_("Vue"),
        required=False,
        choices=[("semaine", _("Semaine")), ("mois", _("Mois"))],
        widget=forms.RadioSelect,
    )
    q = forms.CharField(
        label=_("Recherche"),
        required=False,
        widget=forms.TextInput(
            attrs={"type": "search", "id": "planning-q", "placeholder": _("Filtrer par nom")}
        ),
    )
    service = forms.ChoiceField(
        label=_("Service"), required=False, widget=forms.Select(attrs={"id": "planning-service"})
    )
    site = forms.ChoiceField(
        label=_("Site"), required=False, widget=forms.Select(attrs={"id": "planning-site"})
    )

    def __init__(self, data, *, view: str, services_list, sites):
        data = data.copy()
        data["vue"] = view
        super().__init__(data)
        if services_list is None:
            del self.fields["service"]
        else:
            self.fields["service"].choices = [("", _("Tous les services"))] + [
                (str(item.pk), item.name) for item in services_list
            ]
        self.fields["site"].choices = [("", _("Tous les sites"))] + [
            (str(item.pk), item.name) for item in sites
        ]
