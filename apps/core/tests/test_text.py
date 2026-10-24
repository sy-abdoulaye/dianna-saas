"""Caractères de contrôle et de mise en forme bidirectionnelle retirés de toute saisie
(L6-19) : fonction commune, tous les formulaires, import CSV."""

import pytest
from django import forms

from apps.core.text import strip_unsafe_characters

RLO, ESC, BEL = "‮", "\x1b", "\x07"


def test_control_and_bidi_characters_are_removed_but_tab_and_newline_stay():
    dirty = f"Fac{RLO}ture{ESC}[31m rouge{BEL}⁦x⁩‎\x85\x7f\r\nligne 2\tfin"
    assert strip_unsafe_characters(dirty) == "Facture[31m rougex\nligne 2\tfin"
    assert strip_unsafe_characters("Hélène – « ok » 😀") == "Hélène – « ok » 😀"


def test_every_char_field_of_any_form_is_cleaned_except_passwords():
    class AnyForm(forms.Form):
        title = forms.CharField()
        email = forms.EmailField()
        secret = forms.CharField(widget=forms.PasswordInput)

    form = AnyForm(
        {
            "title": f"Titre{RLO}{ESC}{BEL}",
            "email": f"ada{BEL}@exemple.fr",
            "secret": f"mot{BEL}",
        }
    )
    assert form.is_valid(), form.errors
    assert form.cleaned_data["title"] == "Titre"
    assert form.cleaned_data["email"] == "ada@exemple.fr"
    assert form.cleaned_data["secret"] == f"mot{BEL}"  # jamais modifié


@pytest.mark.django_db
def test_announcement_survey_comment_and_employee_name_are_stored_clean(client_for, company_a):
    from apps.announcements.models import Announcement
    from apps.people.models import Employee
    from apps.people.tests.test_directory import form_data

    client_for(company_a.hr).post(
        "/annonces/nouvelle/",
        {
            "title": f"Paie{RLO}fdp.exe",
            "category": "hr",
            "body": f"Message assez long{ESC}[2J pour être publié{BEL}.",
        },
    )
    announcement = Announcement.all_companies.get(title="Paiefdp.exe")
    assert announcement.body == "Message assez long[2J pour être publié."
    client_for(company_a.hr).post(
        "/annuaire/nouveau/",
        form_data(company_a, last_name=f"Lovelace{RLO}{BEL}", email="ada.propre@exemple.fr"),
    )
    assert Employee.all_companies.filter(last_name="Lovelace").exists()


@pytest.mark.django_db
def test_csv_import_values_are_cleaned(client_for, company_a):
    from apps.people.models import Employee
    from apps.people.tests.test_directory import HEADER, upload

    text = (
        HEADER
        + f"Jean{RLO};Neuf{ESC};jean.neuf@exemple.fr;Comptable;Finance;Lyon;;03/11/2025;CDI\n"
    )
    client = client_for(company_a.admin)
    preview = client.post("/annuaire/import/", {"step": "upload", "file": upload(text)})
    token = preview.content.decode().split('name="token" value="')[1].split('"')[0]
    client.post("/annuaire/import/", {"step": "confirm", "token": token})
    person = Employee.all_companies.get(email="jean.neuf@exemple.fr")
    assert (person.first_name, person.last_name) == ("Jean", "Neuf")


def test_arabic_letter_mark_and_line_and_paragraph_separators_are_removed():
    """U+061C (marque de lettre arabe), U+2028 et U+2029 (séparateurs de ligne et de
    paragraphe, qui coupent une ligne de journal ou de CSV) sont retirés aussi."""
    assert strip_unsafe_characters("a؜b c d") == "abcd"
