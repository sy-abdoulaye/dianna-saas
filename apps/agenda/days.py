"""Jours non ouvrés (T-16, L3-12) : jours fériés et fermetures.

- Jours fériés : paquet `holidays` (France). Un site marqué « Alsace-Moselle » a aussi le
  Vendredi saint et le 26 décembre (L4-02).
- Fermetures : saisies par l'administrateur (`Closure`), pour toute l'entreprise ou un site.

`DayOffs` charge une période en deux requêtes, quel que soit le nombre de personnes : le
planning et les exports l'utilisent pour toute une grille.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from functools import lru_cache

import holidays as holidays_lib
from django.utils.translation import gettext as _

from apps.core.dates import format_date

ALSACE_MOSELLE = "57"  # Moselle : mêmes jours fériés que le Bas-Rhin et le Haut-Rhin


@dataclass(frozen=True)
class DayOff:
    kind: str  # "holiday" ou "closure"
    label: str
    site_closure: bool = False


@lru_cache(maxsize=64)
def _holidays(year: int, alsace: bool) -> dict:
    calendar = holidays_lib.France(
        years=year, subdiv=ALSACE_MOSELLE if alsace else None, language="fr"
    )
    return dict(calendar)


def holidays_between(start: date, end: date, *, alsace: bool = False) -> dict[date, str]:
    found = {}
    for year in range(start.year, end.year + 1):
        for day, label in _holidays(year, alsace).items():
            if start <= day <= end:
                found[day] = label
    return found


class DayOffs:
    """Jours fériés et fermetures d'une période, pour toute l'entreprise courante."""

    def __init__(self, start: date, end: date):
        from apps.agenda.models import Closure
        from apps.core.models import Site

        self.start, self.end = start, end
        self.national = holidays_between(start, end)
        self.alsace = holidays_between(start, end, alsace=True)
        self.alsace_sites = set(
            Site.objects.filter(alsace_moselle=True).values_list("pk", flat=True)
        )
        self.company_closures: dict[date, str] = {}
        self.site_closures: dict[int, dict[date, str]] = {}
        for day, label, site_id in Closure.objects.filter(date__range=(start, end)).values_list(
            "date", "label", "site_id"
        ):
            if site_id is None:
                self.company_closures[day] = label
            else:
                self.site_closures.setdefault(site_id, {})[day] = label

    def get(self, day: date, site_id: int | None) -> DayOff | None:
        holidays = self.alsace if site_id in self.alsace_sites else self.national
        if day in holidays:
            return DayOff("holiday", holidays[day])
        label = self.site_closures.get(site_id, {}).get(day)
        if label:
            return DayOff("closure", label, site_closure=True)
        label = self.company_closures.get(day)
        if label:
            return DayOff("closure", label)
        return None


def day_off(day: date, site_id: int | None) -> DayOff | None:
    return DayOffs(day, day).get(day, site_id)


def day_off_message(day: date, off: DayOff) -> str:
    """Message de refus d'une déclaration sur un jour non ouvré."""
    when = format_date(day, "day_month")
    if off.kind == "holiday":
        return _("Le %(day)s est un jour férié (%(label)s).") % {"day": when, "label": off.label}
    if off.site_closure:
        return _("Votre site est fermé le %(day)s (%(label)s).") % {"day": when, "label": off.label}
    return _("L'entreprise est fermée le %(day)s (%(label)s).") % {"day": when, "label": off.label}


def days(start: date, end: date):
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)
