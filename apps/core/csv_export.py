"""Exports CSV (T-15) : point-virgule, UTF-8 avec BOM pour Excel, cellules neutralisées.

Tout export CSV du projet passe par `csv_content` (ou `safe_row`) : une cellule qui commence
par =, +, -, @, une tabulation ou un retour chariot est préfixée d'une apostrophe, pour
qu'un tableur ne l'exécute pas comme une formule (injection de formules : un nom saisi
« =HYPERLINK(…) » enverrait le contenu du fichier à un tiers à l'ouverture).
"""

import csv
import io
from collections.abc import Iterable

FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")
BOM = "﻿"


def safe_cell(value) -> str:
    text = "" if value is None else str(value)
    if text.startswith(FORMULA_PREFIXES):
        return f"'{text}"
    return text


def safe_row(row: Iterable) -> list[str]:
    return [safe_cell(value) for value in row]


def csv_content(header: Iterable, rows: Iterable[Iterable]) -> str:
    """Contenu complet d'un export : BOM, en-tête puis lignes, toutes neutralisées."""
    buffer = io.StringIO()
    buffer.write(BOM)
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow(safe_row(header))
    for row in rows:
        writer.writerow(safe_row(row))
    return buffer.getvalue()
