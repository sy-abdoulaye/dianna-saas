"""Texte saisi par une personne : retrait des caractères invisibles dangereux (L6-19).

Caractères de contrôle C0 et C1 (sauf tabulation et retour à la ligne) et caractères de mise
en forme bidirectionnelle : ils permettent de maquiller un texte à l'affichage (U+202E
inverse la fin d'un nom de fichier ou d'un titre), d'injecter des séquences de terminal (ESC)
dans un journal ou un export, ou de produire des sons (BEL). Appliqué à tous les champs texte
de tous les formulaires (`install`), et aux fichiers importés."""

import re

from django import forms

# C0 sans \t (09) ni \n (0A) ; DEL et C1 ; U+200E, U+200F ; U+202A à U+202E ; U+2066 à U+2069.
UNSAFE_CHARACTERS = re.compile("[\x00-\x08\x0b-\x1f\x7f-\x9f‎‏‪-‮⁦-⁩]")


def strip_unsafe_characters(value: str) -> str:
    """Retire les caractères de contrôle et de mise en forme bidirectionnelle. Un retour
    chariot (CR) est retiré aussi : les sauts de ligne restent des \\n."""
    return UNSAFE_CHARACTERS.sub("", value)


def install() -> None:
    """Branche le nettoyage sur forms.CharField (et donc EmailField, SlugField, champs des
    ModelForm, d'allauth et de l'administration). Les mots de passe ne sont jamais modifiés."""
    original = forms.CharField.to_python
    if getattr(original, "strips_unsafe_characters", False):
        return

    def to_python(self, value):
        value = original(self, value)
        if isinstance(value, str) and not isinstance(self.widget, forms.PasswordInput):
            value = strip_unsafe_characters(value)
        return value

    to_python.strips_unsafe_characters = True
    forms.CharField.to_python = to_python
