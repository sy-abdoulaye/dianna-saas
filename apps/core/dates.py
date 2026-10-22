"""Format des dates, commun à tout le projet (L5-22). Affichage français :
- « 1er » pour le premier jour du mois (« 1er novembre 2026 ») ;
- jour de la semaine abrégé avec un point (« mer. 21 oct. »).

Dans un gabarit : {{ day|fr_date:"long" }} ; en Python : format_date(day, "long").
"""

import re
from datetime import date, datetime

from django.utils import timezone
from django.utils.formats import date_format

STYLES = {
    "long": "j F Y",  # 21 octobre 2026
    "day_month": "j F",  # 21 octobre
    "full": "l j F Y",  # mercredi 21 octobre 2026
    "weekday_day_month": "l j F",  # mercredi 21 octobre
    "short": "j N",  # 21 oct.
    "short_year": "j N Y",  # 21 oct. 2026
    "month": "F Y",  # octobre 2026
    "numeric": "d/m/Y",  # 21/10/2026
    "day_numeric": "d/m",  # 21/10
    "long_time": "j F Y à H:i",
    "short_time": "j N à H:i",
    "short_year_time": "j N Y à H:i",
}
# Styles avec le jour de la semaine abrégé : « mer. 21 oct. », « mer. 21/10 ».
WEEKDAY_STYLES = {"weekday_short": "j N", "weekday_numeric": "d/m"}
FIRST = re.compile(r"(?<!\d)1 (?=[^\d\W])")


def format_date(value, style: str = "long") -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, datetime) and timezone.is_aware(value):
        value = timezone.localtime(value)
    if style in WEEKDAY_STYLES:
        weekday = date_format(value, "D").rstrip(".") + "."
        return f"{weekday} {_first(value, date_format(value, WEEKDAY_STYLES[style]))}"
    return _first(value, date_format(value, STYLES[style]))


def _first(value, text: str) -> str:
    """« 1 novembre » → « 1er novembre » (seulement le jour du mois, suivi du nom du mois)."""
    day = value.day if isinstance(value, date) else None
    return FIRST.sub("1er ", text, count=1) if day == 1 else text
