"""Exports CSV : neutralisation des formules (apps.core.csv_export)."""

import csv
import io

import pytest

from apps.core.csv_export import BOM, csv_content, safe_cell


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ('=HYPERLINK("https://evil.example")', '\'=HYPERLINK("https://evil.example")'),
        ("+33 1 23 45 67 89", "'+33 1 23 45 67 89"),
        ("-2+3", "'-2+3"),
        ("@SUM(A1)", "'@SUM(A1)"),
        ("\t=1+1", "'\t=1+1"),
        ("\r=1+1", "'\r=1+1"),
        ("Marie Curie", "Marie Curie"),
        ("Coût = 3", "Coût = 3"),  # le signe ailleurs qu'en tête ne compte pas
        ("", ""),
        (None, ""),
        (-5, "'-5"),
        (12, "12"),
    ],
)
def test_safe_cell(value, expected):
    assert safe_cell(value) == expected


def test_csv_content_neutralises_header_and_rows():
    content = csv_content(["=Date"], [["=1+1", "ok"], ["@x", "-y"]])
    assert content.startswith(BOM)
    rows = list(csv.reader(io.StringIO(content.removeprefix(BOM)), delimiter=";"))
    assert rows == [["'=Date"], ["'=1+1", "ok"], ["'@x", "'-y"]]
