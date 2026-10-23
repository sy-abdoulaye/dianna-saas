"""Formulaires des questionnaires. Les contrôles qui dépendent d'autres données (public,
seuil, réponse déjà donnée) sont faits par les services (A3-02)."""

from django import forms
from django.utils.translation import gettext_lazy as _

from apps.surveys.models import (
    COMMENT_MAX,
    QUESTION_MAX,
    TEXT_ANSWER_MAX,
    TITLE_MAX,
    Question,
    Survey,
)
from apps.surveys.services import DraftData

SCALE_CHOICES = [(n, str(n)) for n in range(1, 6)]


class SurveyForm(forms.Form):
    title = forms.CharField(
        label=_("Titre"),
        max_length=TITLE_MAX,
        error_messages={"required": _("Donnez un titre au questionnaire.")},
    )
    audience = forms.ChoiceField(label=_("Public"), choices=Survey.Audience.choices)
    due_date = forms.DateField(
        label=_("Échéance"),
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
    )
    questions = forms.CharField(
        label=_("Questions notées de 1 à 5 (une par ligne)"),
        widget=forms.Textarea(attrs={"rows": 4}),
        error_messages={"required": _("Ajoutez au moins une question.")},
    )
    open_question = forms.CharField(
        label=_("Question ouverte (facultative)"), required=False, max_length=QUESTION_MAX
    )

    def clean_questions(self):
        lines = [line.strip() for line in self.cleaned_data["questions"].splitlines()]
        lines = [line for line in lines if line]
        if not lines:
            raise forms.ValidationError(_("Ajoutez au moins une question."))
        return lines

    def draft_data(self) -> DraftData:
        data = self.cleaned_data
        return DraftData(
            title=data["title"],
            audience=data["audience"],
            due_date=data["due_date"],
            scale_questions=data["questions"],
            open_question=data["open_question"].strip(),
        )

    @classmethod
    def initial_for(cls, survey: Survey) -> dict:
        questions = list(survey.questions.all())
        return {
            "title": survey.title,
            "audience": survey.audience,
            "due_date": survey.due_date,
            "questions": "\n".join(q.label for q in questions if q.kind == Question.Kind.SCALE),
            "open_question": next((q.label for q in questions if q.kind == Question.Kind.TEXT), ""),
        }


class AnswerForm(forms.Form):
    """Un champ par question : note de 1 à 5 et commentaire facultatif, ou réponse libre."""

    def __init__(self, *args, questions, **kwargs):
        super().__init__(*args, **kwargs)
        self.questions = list(questions)
        for question in self.questions:
            if question.kind == Question.Kind.SCALE:
                self.fields[f"q{question.order}"] = forms.TypedChoiceField(
                    label=question.label,
                    choices=SCALE_CHOICES,
                    coerce=int,
                    widget=forms.RadioSelect,
                    help_text=_("1 = pas du tout d'accord · 5 = tout à fait d'accord"),
                    error_messages={"required": _("Choisissez une note de 1 à 5.")},
                )
                self.fields[f"c{question.order}"] = forms.CharField(
                    label=_("Commentaire (facultatif)"),
                    required=False,
                    max_length=COMMENT_MAX,
                    widget=forms.Textarea(
                        attrs={
                            "rows": 2,
                            "placeholder": _("Justifiez votre note si vous le souhaitez"),
                        }
                    ),
                )
            else:
                self.fields[f"q{question.order}"] = forms.CharField(
                    label=question.label,
                    required=False,
                    max_length=TEXT_ANSWER_MAX,
                    help_text=_("Facultatif"),
                    widget=forms.Textarea(attrs={"rows": 3}),
                )

    def rows(self):
        """(question, champ principal, commentaire ou None), dans l'ordre des questions."""
        for question in self.questions:
            comment = self[f"c{question.order}"] if question.kind == Question.Kind.SCALE else None
            yield question, self[f"q{question.order}"], comment

    def answers(self) -> dict:
        """Format attendu par services.submit_answers."""
        data = self.cleaned_data
        result = {}
        for question in self.questions:
            if question.kind == Question.Kind.SCALE:
                result[question.pk] = {
                    "score": data.get(f"q{question.order}"),
                    "comment": data.get(f"c{question.order}", ""),
                }
            else:
                result[question.pk] = {"text": data.get(f"q{question.order}", "")}
        return result


class FilterForm(forms.Form):
    q = forms.CharField(
        label=_("Recherche"),
        required=False,
        widget=forms.TextInput(
            attrs={"type": "search", "placeholder": _("Titre du questionnaire")}
        ),
    )
    statut = forms.ChoiceField(label=_("Statut"), required=False)

    def __init__(self, *args, can_manage=False, **kwargs):
        super().__init__(*args, **kwargs)
        choices = [("", _("Tous")), ("open", _("Ouverts")), ("closed", _("Clos"))]
        if can_manage:
            choices.append(("draft", _("Brouillons")))
        self.fields["statut"].choices = choices
