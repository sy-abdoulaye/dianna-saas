"""Formulaires du suivi d'intervention. Ils ne vérifient que leurs champs, avec deux niveaux :
le brouillon (intervention et période seulement, pourcentages entiers de 0 à 100) et l'envoi
(tous les champs obligatoires). Le doublon et la version sont contrôlés par le service."""

from datetime import date

from django import forms
from django.forms import formset_factory
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core import repeatable
from apps.core.dates import format_date, month_stamp
from apps.core.fields import PercentTextField
from apps.interventions import selectors
from apps.interventions.models import TEXT_MAX, ReportStatus, Visibility
from apps.interventions.services import ItemData, ReportData

DATE = forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")
YES, NO = "oui", "non"


def text(label, *, rows: int = 2, required: bool = False) -> forms.CharField:
    return forms.CharField(
        label=label,
        required=required,
        max_length=TEXT_MAX,
        widget=forms.Textarea(attrs={"rows": rows}),
    )


def month_options() -> list[tuple[str, str]]:
    return [
        (month_stamp(m), format_date(m, "month").capitalize()) for m in selectors.month_choices()
    ]


def parse_month(value: str) -> date | None:
    try:
        year, month = (int(part) for part in value.split("-"))
        return date(year, month, 1)
    except (TypeError, ValueError):
        return None


# ---------- Liste ----------


class ReportFilterForm(forms.Form):
    onglet = forms.CharField(required=False, widget=forms.HiddenInput)
    q = forms.CharField(
        label=_("Recherche"),
        required=False,
        widget=forms.TextInput(attrs={"type": "search", "id": "report-q"}),
    )
    periode = forms.ChoiceField(
        label=_("Période"), required=False, widget=forms.Select(attrs={"id": "report-period"})
    )
    statut = forms.ChoiceField(
        label=_("Statut"),
        required=False,
        choices=[("", _("Tous")), *ReportStatus.choices],
        widget=forms.Select(attrs={"id": "report-status"}),
    )

    def __init__(self, data, *, tab: str, mine: bool):
        data = data.copy()
        data["onglet"] = tab
        super().__init__(data)
        self.fields["periode"].choices = [("", _("Toutes")), *month_options()]
        self.fields["q"].widget.attrs["placeholder"] = (
            _("Intervention") if mine else _("Intervention ou collaborateur")
        )


# ---------- Compte rendu ----------


class ReportForm(forms.Form):
    report = forms.UUIDField(required=False, widget=forms.HiddenInput)
    version = forms.IntegerField(required=False, widget=forms.HiddenInput)
    mission = forms.CharField(
        label=_("Intervention"),
        max_length=160,
        error_messages={"required": _("Indiquez l'intervention concernée.")},
        widget=forms.TextInput(
            attrs={
                "list": "missions",
                "placeholder": _("Ex. Migration de la messagerie · Groupe Horizon"),
                "autocomplete": "off",
            }
        ),
    )
    period = forms.ChoiceField(
        label=_("Période"), error_messages={"required": _("Choisissez la période.")}
    )
    visibility = forms.ChoiceField(
        label=_("Visibilité de l'intervention"),
        required=False,
        choices=[("", _("Choisir…")), *Visibility.choices],
    )
    planned_end = forms.DateField(label=_("Date de fin prévue"), required=False, widget=DATE)
    extension = forms.ChoiceField(
        label=_("Prolongation souhaitée"),
        choices=[(NO, _("Non")), (YES, _("Oui"))],
        initial=NO,
        widget=forms.RadioSelect,
    )
    extension_until = forms.DateField(label=_("Prolongation jusqu'au"), required=False, widget=DATE)
    follow_up = text(_("Points de suivi, risques et besoins"), rows=3)

    def __init__(self, *args, send: bool = False, **kwargs):
        super().__init__(*args, **kwargs)
        self.send = send
        self.fields["period"].choices = month_options()
        self.fields["follow_up"].widget.attrs["placeholder"] = _(
            "Ex. point de clôture à prévoir avec le client"
        )
        if send:
            for name in ("visibility", "planned_end"):
                self.fields[name].required = True
        self.fields["visibility"].error_messages["required"] = _(
            "Choisissez la visibilité de l'intervention."
        )
        self.fields["planned_end"].error_messages["required"] = _("Indiquez la date de fin prévue.")

    def clean_period(self) -> date:
        period = parse_month(self.cleaned_data["period"])
        if period is None:
            raise forms.ValidationError(_("Choisissez la période."))
        return period

    def clean(self):
        data = super().clean()
        wanted = data.get("extension") == YES
        until, end = data.get("extension_until"), data.get("planned_end")
        if wanted and self.send and not until:
            self.add_error("extension_until", _("Indiquez jusqu'à quand."))
        if wanted and until and end and until <= end:
            self.add_error(
                "extension_until", _("La prolongation doit aller au-delà de la fin prévue.")
            )
        return data


class ItemForm(forms.Form):
    """Un travail (réalisé ou prévu). À l'envoi, la description et le pourcentage sont
    obligatoires pour chaque bloc saisi."""

    description = text(_("Descriptif"))
    completion = PercentTextField(label=_("Réalisation"), required=False)
    due_date = forms.DateField(label=_("Délai"), required=False, widget=DATE)
    comments = text(_("Commentaires"))
    missing_description = _("Décrivez le travail réalisé.")

    def __init__(self, *args, send: bool = False, **kwargs):
        super().__init__(*args, **kwargs)
        self.send = send
        for name in ("comments",):
            self.fields[name].widget.attrs["placeholder"] = _("Facultatif")

    def clean(self):
        data = super().clean()
        if not self.send:
            return data
        if not (data.get("description") or "").strip():
            self.add_error("description", self.missing_description)
        if data.get("completion") is None and "completion" not in self.errors:
            self.add_error("completion", _("Indiquez un pourcentage entre 0 et 100."))
        return data

    def item(self) -> ItemData:
        data = self.cleaned_data
        return ItemData(
            description=data.get("description", "").strip(),
            completion=data.get("completion"),
            due_date=data.get("due_date"),
            comments=data.get("comments", ""),
            difficulties=data.get("difficulties", ""),
            solutions=data.get("solutions", ""),
        )


class DoneItemForm(ItemForm):
    difficulties = text(_("Difficultés rencontrées"))
    solutions = text(_("Solutions proposées"))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("difficulties", "solutions"):
            self.fields[name].widget.attrs["placeholder"] = _("Facultatif")


class NextItemForm(ItemForm):
    missing_description = _("Décrivez le travail prévu.")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["description"].label = _("Description des travaux")
        self.fields["completion"].label = _("Réalisation visée")


class DoneFormSet(repeatable.RepeatableFormSet):
    def clean(self):
        super().clean()
        send = self.form_kwargs.get("send", False)
        if send and not any(form.errors for form in self.forms) and not self.kept():
            raise forms.ValidationError(_("Ajoutez au moins un travail réalisé."))


DoneItems = formset_factory(DoneItemForm, formset=DoneFormSet, extra=0, can_delete=True, max_num=50)
NextItems = formset_factory(
    NextItemForm, formset=repeatable.RepeatableFormSet, extra=0, can_delete=True, max_num=50
)

repeatable.register(
    "interventions-done",
    repeatable.Repeatable(
        DoneItems, "done", "interventions/partials/done_fields.html", _("Travail réalisé")
    ),
)
repeatable.register(
    "interventions-next",
    repeatable.Repeatable(
        NextItems, "next", "interventions/partials/next_fields.html", _("Travail prévu")
    ),
)


def formsets(data=None, *, send: bool = False, report=None, initial=None):
    """(travaux réalisés, travaux prévus) : depuis l'envoi, le compte rendu, ou un bloc vide."""
    done_initial = next_initial = initial
    if data is None and report is not None:
        items = list(report.items.all())
        done_initial = [_item_initial(i) for i in items if i.section == "done"] or [{}]
        next_initial = [_item_initial(i) for i in items if i.section == "next"] or [{}]
    elif data is None:
        done_initial = next_initial = [{}]
    kwargs = {"form_kwargs": {"send": send}}
    return (
        DoneItems(data, prefix="done", initial=done_initial, **kwargs),
        NextItems(data, prefix="next", initial=next_initial, **kwargs),
    )


def _item_initial(item) -> dict:
    return {
        "description": item.description,
        "completion": item.completion,
        "due_date": item.due_date,
        "comments": item.comments,
        "difficulties": item.difficulties,
        "solutions": item.solutions,
    }


def report_data(form: ReportForm, done, next_items) -> ReportData:
    data = form.cleaned_data
    wanted = data.get("extension") == YES
    return ReportData(
        mission=data["mission"].strip(),
        period=data["period"],
        visibility=data.get("visibility") or "",
        planned_end=data.get("planned_end"),
        extension_wanted=wanted,
        extension_until=data.get("extension_until") if wanted else None,
        follow_up=data.get("follow_up", ""),
        done=[f.item() for f in done.kept()],
        next=[f.item() for f in next_items.kept()],
    )


def report_initial(report=None, last=None) -> dict:
    """Valeurs du formulaire : le compte rendu modifié, ou celles du dernier compte rendu de
    la personne (intervention et visibilité, fiche 11)."""
    source = report or last
    initial = {"period": month_stamp(timezone.localdate().replace(day=1)), "extension": NO}
    if source is not None:
        initial.update(
            {
                "mission": source.mission.name,
                "visibility": source.visibility,
                "planned_end": source.planned_end,
                "extension": YES if source.extension_wanted else NO,
                "extension_until": source.extension_until,
            }
        )
    if report is not None:
        initial.update(
            {
                "report": report.public_id,
                "version": report.version,
                "period": month_stamp(report.period),
                "follow_up": report.follow_up,
            }
        )
    return initial


class DecisionForm(forms.Form):
    note = text(_("Commentaire"), rows=3)

    def __init__(self, *args, approve: bool, **kwargs):
        super().__init__(*args, **kwargs)
        if approve:
            self.fields["note"].help_text = _("Facultatif. Transmis au collaborateur.")
        else:
            self.fields["note"].label = _("Ce qu'il faut compléter")
            self.fields["note"].required = True
            self.fields["note"].error_messages["required"] = _("Précisez ce qu'il faut compléter.")
