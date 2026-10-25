"""Blocs répétables d'un formulaire long (objectifs d'un entretien, travaux d'un compte rendu,
docs/02-architecture.md, section HTMX).

Chaque usage s'inscrit une fois (`register`) avec son formset et le gabarit des champs d'un
bloc. « Ajouter » appelle la vue commune `apps.core.views.add_block`, qui renvoie un seul bloc
vide à l'index suivant et met à jour le compteur du formset : les blocs déjà saisis ne sont
jamais renvoyés, donc jamais vidés. « Retirer » se fait dans le navigateur (ui.js) : le bloc
est masqué et coché pour suppression, et « Annuler » dans la notification le fait revenir.
"""

from dataclasses import dataclass

from django import forms
from django.forms import BaseFormSet
from django.utils.functional import Promise

# Au-delà, un ajout est refusé (garde-fou ; chaque formset a aussi son propre maximum).
ABSOLUTE_MAX = 50


@dataclass(frozen=True)
class Repeatable:
    """`formset` : classe de formset (préfixe fixe) ; `fields_template` : champs d'un bloc ;
    `row_label` : titre d'un bloc, numéroté (« Travail réalisé 2 »)."""

    formset: type[BaseFormSet]
    prefix: str
    fields_template: str
    row_label: str | Promise


BLOCKS: dict[str, Repeatable] = {}


def register(name: str, block: Repeatable) -> None:
    if name in BLOCKS:
        raise ValueError(f"Bloc répétable déjà inscrit : {name}")
    BLOCKS[name] = block


class RepeatableFormSet(BaseFormSet):
    """Base des formsets répétables : la suppression est un champ caché (cochée par ui.js) ;
    `kept()` donne les blocs gardés qui contiennent au moins une saisie."""

    deletion_widget = forms.HiddenInput

    def kept(self) -> list[forms.Form]:
        return [
            form
            for form in self.forms
            if not (self.can_delete and self._should_delete_form(form))
            and any(value not in (None, "", False) for value in form.cleaned_data.values())
        ]
