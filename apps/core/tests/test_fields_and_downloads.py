"""Briques communes du lot 7 : pourcentage saisi en texte (Q9) et fichier à télécharger."""

import pytest
from django import forms

from apps.core.fields import PercentTextField
from apps.core.http import attachment


class PercentForm(forms.Form):
    completion = PercentTextField(required=False)


@pytest.mark.parametrize(
    ("raw", "value"), [("0", 0), ("75", 75), ("100", 100), (" 80 % ", 80), ("", None)]
)
def test_a_percentage_is_an_integer_from_0_to_100(raw, value):
    form = PercentForm({"completion": raw})
    assert form.is_valid() and form.cleaned_data["completion"] == value


@pytest.mark.parametrize("raw", ["150", "-5", "12,5", "abc", "1000"])
def test_any_other_percentage_says_between_0_and_100(raw):
    form = PercentForm({"completion": raw})
    assert not form.is_valid()
    assert form.errors["completion"] == ["Entre 0 et 100."]


def test_a_percentage_field_is_text_with_a_numeric_keyboard():
    html = str(PercentForm()["completion"])
    assert 'type="text"' in html and 'inputmode="numeric"' in html


def test_attachment_names_the_file_chosen_by_the_application():
    response = attachment(b"data", "text/csv; charset=utf-8", "journal.csv")
    assert response["Content-Disposition"] == 'attachment; filename="journal.csv"'
    assert response["Content-Type"] == "text/csv; charset=utf-8"
