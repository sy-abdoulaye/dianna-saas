"""Format commun des dates (apps/core/dates.py, L5-22)."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from django.template import Context, Template
from django.utils import translation

from apps.core.dates import format_date


@pytest.fixture(autouse=True)
def french():
    with translation.override("fr"):
        yield


@pytest.mark.parametrize(
    ("style", "first", "other"),
    [
        ("long", "1er novembre 2026", "21 octobre 2026"),
        ("day_month", "1er novembre", "21 octobre"),
        ("full", "dimanche 1er novembre 2026", "mercredi 21 octobre 2026"),
        ("short", "1er nov.", "21 oct."),
        ("weekday_short", "dim. 1er nov.", "mer. 21 oct."),
        ("month", "novembre 2026", "octobre 2026"),
        ("numeric", "01/11/2026", "21/10/2026"),
    ],
)
def test_styles(style, first, other):
    assert format_date(date(2026, 11, 1), style) == first
    assert format_date(date(2026, 10, 21), style) == other


def test_only_the_first_day_gets_er():
    assert format_date(date(2026, 11, 11), "long") == "11 novembre 2026"
    assert format_date(date(2026, 11, 21), "long") == "21 novembre 2026"


def test_monday_header_and_aware_datetime_in_paris_time():
    assert format_date(date(2026, 10, 19), "weekday_short") == "lun. 19 oct."
    utc = datetime(2026, 10, 31, 23, 30, tzinfo=ZoneInfo("UTC"))  # 1er novembre 0 h 30 à Paris
    assert format_date(utc, "long_time") == "1er novembre 2026 à 00:30"


def test_empty_value_and_template_filter():
    assert format_date(None) == ""
    rendered = Template('{% load ui %}{{ day|fr_date:"day_month" }}').render(
        Context({"day": date(2026, 11, 1)})
    )
    assert rendered == "1er novembre"
