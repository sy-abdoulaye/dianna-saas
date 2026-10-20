"""Formats d'export communs : iCalendar (RFC 5545), Excel neutralisé, PDF et logo."""

import io
from datetime import UTC, date, datetime

import pytest
from django.core.files.base import ContentFile
from openpyxl import load_workbook

from apps.core import pdf
from apps.core.ics_export import IcsEvent, escape, fold, ics_content
from apps.core.models import Company
from apps.core.tokens import color, light_tokens
from apps.core.xlsx_export import Styled, xlsx_content
from apps.people.tests.conftest import image_bytes, private_media  # noqa: F401


def test_ics_escapes_text_values():
    assert escape("a;b,c\\d\ne") == "a\\;b\\,c\\\\d\\ne"


def test_ics_folds_long_lines_without_cutting_a_character():
    line = "SUMMARY:" + "é" * 60
    folded = fold(line)
    parts = folded.split("\r\n ")
    assert len(parts) > 1
    assert all(len(part.encode()) <= 75 for part in parts)
    assert "".join(parts) == line


def test_ics_all_day_events_end_the_next_day():
    content = ics_content(
        [IcsEvent("telework-1@x", date(2026, 12, 31), date(2026, 12, 31), "Télétravail · A")],
        name="Planning",
        stamp=datetime(2026, 10, 21, 8, 0, tzinfo=UTC),
    )
    assert "DTSTART;VALUE=DATE:20261231\r\n" in content
    assert "DTEND;VALUE=DATE:20270101\r\n" in content
    assert "DTSTAMP:20261021T080000Z\r\n" in content
    assert "STATUS:CONFIRMED" in content


def test_xlsx_formulas_stay_text_and_numbers_stay_numbers():
    data = xlsx_content(
        "=Titre",
        ["Nom", "Jours"],
        [['=HYPERLINK("https://exemple.test")', 3], [Styled("+1", "site-bg", "site-ink"), 2.5]],
    )
    sheet = load_workbook(io.BytesIO(data)).active
    assert sheet.title == "'=Titre"
    assert sheet["A2"].value.startswith("'=") and sheet["A2"].data_type == "s"
    assert sheet["A3"].value == "'+1" and sheet["A3"].fill.fgColor.rgb.endswith(color("site-bg"))
    assert sheet["B2"].value == 3 and sheet["B3"].value == 2.5


def test_tokens_come_from_app_css():
    tokens = light_tokens()
    assert tokens["site-bg"].startswith("#") and color("tel-bg") == tokens["tel-bg"][1:].upper()


@pytest.mark.django_db
def test_pdf_fetcher_serves_the_current_company_logo_only(company_a, private_media):  # noqa: F811
    company = Company.objects.get(pk=company_a.company.pk)
    company.logo.save("logo.png", ContentFile(image_bytes()), save=True)
    fetcher = pdf.DiannaURLFetcher(company)
    response = fetcher.fetch(pdf.LOGO_URL)
    assert response.headers["Content-Type"] == "image/png"
    with pytest.raises(pdf.URLRefusedError):
        pdf.DiannaURLFetcher(None).fetch(pdf.LOGO_URL)
