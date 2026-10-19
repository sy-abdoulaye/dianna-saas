import pytest

pytestmark = pytest.mark.django_db


def test_admin_dashboard_shows_platform_indicators(client_for, company_a):
    content = client_for(company_a.admin).get("/").content.decode()
    for label in ("Utilisateurs actifs", "Modules activés", "Services", "Événements du journal"):
        assert label in content
    assert "10 / 10" in content
    assert 'href="/administration/"' in content


def test_hr_dashboard_shows_headcount(client_for, company_a):
    content = client_for(company_a.hr).get("/").content.decode()
    assert "Effectif en poste" in content and "Arrivées à venir" in content


def test_employee_dashboard_has_no_fake_indicators(client_for, company_a):
    content = client_for(company_a.employee).get("/").content.decode()
    assert "kpi-value" not in content
    assert "Tout est à jour" in content
    assert "Déclarer du télétravail" not in content  # module du lot 3
    assert 'href="/annuaire/"' in content
