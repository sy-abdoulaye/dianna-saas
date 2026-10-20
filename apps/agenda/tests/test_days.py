"""Jours non ouvrés (T-16, L3-12) : jours fériés, Alsace-Moselle par site, fermetures."""

from datetime import date

import pytest

from apps.agenda.days import DayOffs, day_off, day_off_message, holidays_between
from apps.agenda.models import Closure
from apps.core.models import Site
from apps.core.tenancy import tenant_context
from tests.factories import SiteFactory

pytestmark = pytest.mark.django_db


def test_french_holidays_with_their_label():
    found = holidays_between(date(2026, 12, 1), date(2026, 12, 31))
    assert found == {date(2026, 12, 25): "Noël"}
    assert date(2026, 5, 1) in holidays_between(date(2026, 1, 1), date(2026, 12, 31))


def test_alsace_moselle_is_a_setting_of_the_site(company_a):
    with tenant_context(company_a.company):
        strasbourg = SiteFactory(company=company_a.company, name="Strasbourg", alsace_moselle=True)
        offs = DayOffs(date(2026, 12, 24), date(2026, 12, 26))
        assert offs.get(date(2026, 12, 26), strasbourg.pk).label == "Saint-Étienne"
        assert offs.get(date(2026, 12, 26), company_a.site.pk) is None
        assert offs.get(date(2026, 4, 3), strasbourg.pk) is None  # hors période chargée
        assert day_off(date(2026, 4, 3), strasbourg.pk).label == "Vendredi saint"


def test_closures_for_the_company_or_one_site(company_a):
    with tenant_context(company_a.company):
        paris = Site.objects.create(name="Paris")
        Closure.objects.create(
            date=date(2026, 12, 24), label="Fermeture du site", site=company_a.site
        )
        Closure.objects.create(date=date(2026, 12, 31), label="Inventaire")
        offs = DayOffs(date(2026, 12, 21), date(2026, 12, 31))
        lyon = offs.get(date(2026, 12, 24), company_a.site.pk)
        assert lyon.kind == "closure" and lyon.site_closure
        assert offs.get(date(2026, 12, 24), paris.pk) is None
        assert offs.get(date(2026, 12, 31), paris.pk).label == "Inventaire"
        assert day_off_message(date(2026, 12, 24), lyon) == (
            "Votre site est fermé le 24 décembre (Fermeture du site)."
        )
        noel = offs.get(date(2026, 12, 25), paris.pk)
        assert day_off_message(date(2026, 12, 25), noel) == (
            "Le 25 décembre est un jour férié (Noël)."
        )


def test_closures_are_isolated_between_companies(company_a, company_b):
    with tenant_context(company_b.company):
        Closure.objects.create(date=date(2026, 12, 28), label="Fermeture de B")
    with tenant_context(company_a.company):
        assert DayOffs(date(2026, 12, 28), date(2026, 12, 28)).get(date(2026, 12, 28), None) is None
