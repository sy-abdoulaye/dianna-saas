"""Tableau de bord complet (docs/modules/02-tableau-de-bord.md, lot 4)."""

import re
from html import unescape

import pytest

from apps.approvals.views import menu_counts
from apps.core.models import CompanyModule, Module
from apps.core.tenancy import tenant_context

pytestmark = pytest.mark.django_db


def kpis(content):
    pattern = r'<span class="kpi-label">([^<]+)</span>\s*<b class="kpi-value">([^<]+)</b>'
    return {unescape(k): unescape(v) for k, v in re.findall(pattern, content)}


def test_admin_dashboard_shows_platform_indicators(client_for, company_a):
    content = client_for(company_a.admin).get("/").content.decode()
    assert set(kpis(content)) == {
        "Utilisateurs actifs",
        "Modules activés",
        "Services",
        "Événements du journal",
    }
    assert "10 / 10" in content
    assert 'href="/administration/"' in content
    assert "Mes dernières demandes" not in content


def test_employee_dashboard(client_for, company_a):
    content = client_for(company_a.employee).get("/").content.decode()
    values = kpis(content)
    assert values["Télétravail cette semaine"].endswith("/ 2")
    # Télétravail, congés, astreinte, justificatif de transport ; la demande de matériel de
    # la fixture est validée.
    assert values["Mes demandes en attente"] == "4"
    assert values["Matériel attribué"] == "1"
    # Quatre indicateurs, comme le prototype : les annonces non lues (lot 6) remplacent
    # « Mes prochains congés », affiché seulement s'il reste une place (L4-08).
    assert values["Annonces non lues"] == "1" and len(values) == 4  # annonce de la fixture
    assert "Tout est à jour" in content
    assert "Déclarer du télétravail" in content
    assert "Mes dernières demandes" in content
    assert "Voir le planning" in content
    assert "Mon matériel" in content  # raccourci du lot 5
    assert 'id="h-announcements"' in content  # bloc « Annonces » (lot 6)


def test_manager_todo_matches_the_menu_and_leads_to_the_action(client_for, company_a):
    client = client_for(company_a.manager)
    content = client.get("/").content.decode()
    assert "1 demande de télétravail à valider" in content
    assert 'href="/teletravail/?onglet=a-valider"' in content
    values = kpis(content)
    assert values["Demandes à valider"] == "3"
    assert "Équipe sur site aujourd'hui" in values and "En télétravail aujourd'hui" in values


def test_counters_are_identical_to_the_menu(client_for, company_a):
    response = client_for(company_a.manager).get("/")
    request = response.wsgi_request
    with tenant_context(company_a.company):
        total = sum(menu_counts(request).values())
    assert kpis(response.content.decode())["Demandes à valider"] == str(total)


def test_hr_dashboard(client_for, company_a):
    content = client_for(company_a.hr).get("/").content.decode()
    values = kpis(content)
    assert {"Effectif en poste", "Arrivées à venir", "Demandes à valider"} <= set(values)
    assert values["Justificatifs à valider"] == "1"  # celui de la fixture
    assert "1 demande de justificatif de transport à valider" in content
    assert 'href="/transport/?onglet=a-valider"' in content
    assert values["Vœux de la campagne"] == "1"


def test_disabled_modules_appear_in_no_block(client_for, company_a):
    CompanyModule.all_companies.filter(company=company_a.company).exclude(
        module=Module.ANNOUNCEMENTS
    ).update(enabled=False)
    content = client_for(company_a.manager).get("/").content.decode()
    assert kpis(content) == {}
    assert "Tout est à jour" in content
    for absent in ("Voir le planning", "Déclarer du télétravail", "Mes dernières demandes"):
        assert absent not in content
    assert "à valider" not in content
