"""Formulaires de la carrière : ils ne vérifient que leurs champs ; l'étape, la personne qui
agit, les doublons et les chevauchements sont contrôlés par les services (A3-02)."""

from datetime import date

from django import forms
from django.forms import formset_factory
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.careers import selectors
from apps.careers.models import (
    TEXT_MAX,
    Competency,
    FollowUpNote,
    Review,
    ReviewKind,
    ReviewReason,
)
from apps.core import repeatable
from apps.people.models import Employee

DATE = forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")
SELF_MIN = 20
NOTE_MIN = 8
OBJECTIVES_MAX = 5
TRAININGS_MAX = 20
REQUIRED = _("Ce champ est obligatoire.")


def long_text(label, *, required: bool = True, rows: int = 4, **kwargs) -> forms.CharField:
    return forms.CharField(
        label=label,
        required=required,
        max_length=TEXT_MAX,
        widget=forms.Textarea(attrs={"rows": rows}),
        error_messages={"required": REQUIRED},
        **kwargs,
    )


# ---------- Liste et lancement ----------


PROGRESS_CHOICES = [
    ("", _("Tous")),
    ("a-faire", _("À faire par moi")),
    ("en-cours", _("En cours")),
    ("clos", _("Clos")),
]


class ReviewFilterForm(forms.Form):
    onglet = forms.CharField(required=False, widget=forms.HiddenInput)
    q = forms.CharField(
        label=_("Recherche"),
        required=False,
        widget=forms.TextInput(
            attrs={"type": "search", "placeholder": _("Collaborateur"), "id": "career-q"}
        ),
    )
    type = forms.ChoiceField(
        label=_("Type"),
        required=False,
        choices=[("", _("Tous les types")), *ReviewKind.choices],
        widget=forms.Select(attrs={"id": "career-type"}),
    )
    avancement = forms.ChoiceField(
        label=_("Avancement"),
        required=False,
        choices=PROGRESS_CHOICES,
        widget=forms.Select(attrs={"id": "career-progress"}),
    )

    def __init__(self, data, *, tab: str):
        data = data.copy()
        data["onglet"] = tab
        super().__init__(data)


class FollowUpFilterForm(forms.Form):
    onglet = forms.CharField(required=False, widget=forms.HiddenInput)
    q = forms.CharField(
        label=_("Recherche"),
        required=False,
        widget=forms.TextInput(
            attrs={
                "type": "search",
                "placeholder": _("Rechercher un collaborateur"),
                "id": "followup-q",
            }
        ),
    )

    def __init__(self, data, *, tab: str):
        data = data.copy()
        data["onglet"] = tab
        super().__init__(data)


class LaunchForm(forms.Form):
    employee = forms.ModelChoiceField(
        label=_("Collaborateur"),
        queryset=Employee.objects.none(),
        empty_label=_("Choisir…"),
        error_messages={"required": _("Choisissez un collaborateur.")},
    )
    kind = forms.ChoiceField(label=_("Type d'entretien"), choices=ReviewKind.choices)
    reason = forms.ChoiceField(
        label=_("Motif"),
        required=False,
        choices=[("", _("Choisir…")), *ReviewReason.choices],
        help_text=_("Entretien de parcours professionnel seulement."),
    )

    def __init__(self, *args, viewer: Employee, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["employee"].queryset = selectors.launch_candidates(viewer)
        self.fields["employee"].label_from_instance = lambda person: person.full_name

    def clean(self):
        data = super().clean()
        if data.get("kind") == ReviewKind.PROFESSIONAL and not data.get("reason"):
            self.add_error("reason", _("Choisissez le motif de l'entretien de parcours."))
        return data


class CampaignForm(forms.Form):
    label = forms.CharField(
        label=_("Libellé"),
        max_length=80,
        error_messages={"required": _("Indiquez le libellé de la campagne.")},
        widget=forms.TextInput(attrs={"placeholder": _("Ex. Campagne 2026")}),
    )
    start = forms.DateField(label=_("Début"), widget=DATE)
    end = forms.DateField(label=_("Fin"), widget=DATE)

    def clean(self):
        data = super().clean()
        if data.get("start") and data.get("end") and data["end"] < data["start"]:
            self.add_error("end", _("La fin doit être après le début."))
        return data


# ---------- Étapes ----------


class SelfForm(forms.Form):
    summary = long_text(_("Bilan de l'année"), rows=5)
    project = long_text(_("Projet professionnel et souhaits d'évolution"), required=False, rows=3)

    def __init__(self, *args, review: Review, **kwargs):
        super().__init__(*args, **kwargs)
        if review.kind == ReviewKind.PROFESSIONAL:
            self.fields["summary"].label = _("Parcours depuis le dernier entretien")
            self.fields["project"].required = True
        else:
            del self.fields["project"]

    def clean_summary(self):
        summary = self.cleaned_data["summary"].strip()
        if len(summary) < SELF_MIN:
            raise forms.ValidationError(_("Développez un peu : au moins 20 caractères."))
        return summary


class ObjectiveForm(forms.Form):
    title = forms.CharField(label=_("Objectif"), max_length=200, required=False)
    due_date = forms.DateField(label=_("Échéance"), required=False, widget=DATE)

    def clean(self):
        data = super().clean()
        if data.get("title") and not data.get("due_date"):
            self.add_error("due_date", _("Indiquez l'échéance."))
        if data.get("due_date") and not data.get("title"):
            self.add_error("title", _("Décrivez l'objectif."))
        return data


class ObjectiveFormSet(repeatable.RepeatableFormSet):
    def clean(self):
        super().clean()
        if any(form.errors for form in self.forms):
            return
        kept = self.kept()
        if not kept:
            raise forms.ValidationError(_("Indiquez au moins un objectif."))
        if len(kept) > OBJECTIVES_MAX:
            raise forms.ValidationError(_("Cinq objectifs au plus."))


Objectives = formset_factory(
    ObjectiveForm, formset=ObjectiveFormSet, extra=0, can_delete=True, max_num=50
)

repeatable.register(
    "careers-objectives",
    repeatable.Repeatable(
        Objectives, "objectives", "careers/partials/objective_fields.html", _("Objectif")
    ),
)


def objectives_formset(data=None, review: Review | None = None) -> forms.BaseFormSet:
    initial = None
    if data is None:
        saved = list(review.objectives.values("title", "due_date")) if review else []
        initial = saved or [{"due_date": date(timezone.localdate().year + 1, 6, 30)}]
    return Objectives(data, prefix="objectives", initial=initial)


class EvaluationForm(forms.Form):
    """Évaluation du manager (entretien individuel) : un champ de note par compétence active."""

    summary = long_text(_("Votre bilan"))
    strengths = long_text(_("Points forts"), rows=3)
    improvements = long_text(_("Axes de progrès"), rows=3)

    def __init__(self, *args, competencies: list[Competency], **kwargs):
        super().__init__(*args, **kwargs)
        self.competencies = competencies
        for competency in competencies:
            self.fields[self.rating_name(competency)] = forms.TypedChoiceField(
                label=competency.name,
                help_text=competency.description,
                choices=[(n, str(n)) for n in range(1, 5)],
                coerce=int,
                widget=forms.RadioSelect,
                error_messages={"required": _("Notez toutes les compétences de 1 à 4.")},
            )

    @staticmethod
    def rating_name(competency: Competency) -> str:
        return f"rating_{competency.pk}"

    def rating_fields(self) -> list:
        return [self[self.rating_name(c)] for c in self.competencies]

    def ratings(self) -> dict[int, int]:
        return {c.pk: self.cleaned_data[self.rating_name(c)] for c in self.competencies}


class MeetingForm(forms.Form):
    meeting_date = forms.DateField(
        label=_("Date de l'entretien"),
        widget=DATE,
        error_messages={"required": _("Choisissez une date.")},
    )
    place = forms.CharField(
        label=_("Lieu"),
        max_length=120,
        required=False,
        widget=forms.TextInput(attrs={"list": "meeting-places"}),
        help_text=_("Facultatif. Ex. salle de réunion, visioconférence."),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["meeting_date"].widget.attrs["min"] = timezone.localdate().isoformat()


CRITERIA_CHOICES = [("", _("Non renseigné")), ("yes", _("Oui")), ("no", _("Non"))]
CRITERIA = (
    ("summary_training", _("Au moins une action de formation")),
    ("summary_certification", _("Une certification")),
    ("summary_progression", _("Une progression salariale ou professionnelle")),
)


class ParcoursReportForm(forms.Form):
    """Compte rendu de l'entretien de parcours ; bloc « État des lieux à 8 ans » au motif
    « état des lieux » (M-08, règles légales à confirmer par un juriste)."""

    report = long_text(_("Compte rendu"), rows=5)
    trainings = forms.CharField(
        label=_("Formations retenues (une par ligne)"),
        required=False,
        max_length=TEXT_MAX,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text=_("Facultatif"),
    )
    next_review_due = forms.DateField(
        label=_("Prochain entretien de parcours avant le"), required=False, widget=DATE
    )
    next_summary_due = forms.DateField(
        label=_("Prochain état des lieux avant le"), required=False, widget=DATE
    )

    def __init__(self, *args, review: Review, **kwargs):
        super().__init__(*args, **kwargs)
        self.is_summary = review.is_summary
        if self.is_summary:
            for name, label in CRITERIA:
                self.fields[name] = forms.ChoiceField(
                    label=label, required=False, choices=CRITERIA_CHOICES
                )

    def clean_trainings(self) -> list[str]:
        lines = [line.strip() for line in self.cleaned_data["trainings"].splitlines()]
        lines = [line[:200] for line in lines if line]
        if len(lines) > TRAININGS_MAX:
            raise forms.ValidationError(_("Vingt formations au plus."))
        return lines

    def criteria(self) -> tuple[bool | None, bool | None, bool | None]:
        values = {"yes": True, "no": False}
        if not self.is_summary:
            return (None, None, None)
        training, certification, progression = (
            values.get(self.cleaned_data.get(name, "")) for name, _label in CRITERIA
        )
        return training, certification, progression

    def criteria_fields(self) -> list:
        return [self[name] for name, _label in CRITERIA] if self.is_summary else []


class SignForm(forms.Form):
    comment = long_text(
        _("Votre commentaire (facultatif)"),
        required=False,
        rows=3,
        help_text=_("Ajouté au compte rendu avant votre signature."),
    )


# ---------- Notes de suivi ----------


class NoteForm(forms.Form):
    kind = forms.ChoiceField(label=_("Type"), choices=FollowUpNote.Kind.choices)
    text = long_text(_("Note"))
    is_private = forms.BooleanField(
        label=_("Note privée (visible uniquement par moi)"), required=False
    )

    def __init__(self, *args, own_file: bool, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["text"].error_messages["required"] = _("Écrivez le contenu de la note.")
        if own_file:
            # Sur sa propre fiche : un souhait, jamais privé (décision du lot 7).
            self.fields["kind"].choices = [(FollowUpNote.Kind.WISH, FollowUpNote.Kind.WISH.label)]
            del self.fields["is_private"]

    def clean_text(self):
        text = self.cleaned_data["text"].strip()
        if len(text) < NOTE_MIN:
            raise forms.ValidationError(_("La note est trop courte (8 caractères minimum)."))
        return text
