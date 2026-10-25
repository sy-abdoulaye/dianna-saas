"""Onglet « Compétences » (fiche 04, lot 7) et réglages de l'entretien de parcours."""

import json

import pytest

from apps.careers.models import Competency
from apps.core.models import AuditLog, Company
from apps.core.tenancy import tenant_context

pytestmark = pytest.mark.django_db
HX = {"HX-Request": "true"}
CAREER = {"career_review_interval_years": "4", "career_summary_interval_years": "8"}


def names(company) -> list[str]:
    with tenant_context(company):
        return list(Competency.objects.values_list("name", flat=True))


def test_competencies_are_reserved_to_the_administrator(client_for, company_a):
    assert client_for(company_a.hr).get("/administration/competences/").status_code == 403
    page = client_for(company_a.admin).get("/administration/competences/").content.decode()
    assert "Relation client" in page and "Maîtrise des outils" in page


def test_add_rename_reorder_and_deactivate_a_competency(client_for, company_a):
    client = client_for(company_a.admin)
    added = client.post(
        "/administration/competences/ajouter/", {"name": "Pédagogie", "description": ""}, headers=HX
    )
    assert json.loads(added["HX-Trigger"])["competenciesChanged"]
    with tenant_context(company_a.company):
        pedagogy = Competency.objects.get(name="Pédagogie")
    client.post(f"/administration/competences/{pedagogy.pk}/monter/", headers=HX)
    assert names(company_a.company)[3] == "Pédagogie"
    client.post(
        f"/administration/competences/{pedagogy.pk}/modifier/",
        {"name": "Transmission", "description": "Former les autres"},
        headers=HX,
    )
    confirm = client.get(f"/administration/competences/{pedagogy.pk}/activation/")
    assert "Les notes déjà données sont conservées." in confirm.content.decode()
    client.post(f"/administration/competences/{pedagogy.pk}/activation/", headers=HX)
    with tenant_context(company_a.company):
        pedagogy.refresh_from_db()
    assert pedagogy.name == "Transmission" and not pedagogy.active
    actions = set(AuditLog.all_companies.values_list("action", flat=True))
    assert {"company.competency_added", "company.competency_disabled"} <= actions


def test_a_duplicate_competency_name_is_refused(client_for, company_a):
    response = client_for(company_a.admin).post(
        "/administration/competences/ajouter/", {"name": "autonomie"}, headers=HX
    )
    assert response.status_code == 422
    assert "Cette compétence existe déjà." in response.content.decode()


def test_career_intervals_are_limited_to_four_and_eight_years(client_for, company_a):
    client = client_for(company_a.admin)
    bad = client.post(
        "/administration/",
        {
            "name": "Exemple SAS",
            "telework_max_per_week": "2",
            "career_review_interval_years": "5",
            "career_summary_interval_years": "9",
        },
    )
    content = bad.content.decode()
    assert "entre 1 et 4" in content and "entre 1 et 8" in content
    assert "Règles légales à confirmer par un juriste." in content
    client.post(
        "/administration/",
        {
            "name": "Exemple SAS",
            "telework_max_per_week": "2",
            **CAREER,
            "career_review_interval_years": "3",
        },
    )
    assert Company.objects.get(pk=company_a.company.pk).career_review_interval_years == 3
