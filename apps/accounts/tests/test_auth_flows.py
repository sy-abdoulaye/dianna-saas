"""Connexion, mot de passe oublié, double authentification, hôte éditeur (fiche socle)."""

import pytest
from django.core import mail
from django.core.management import call_command
from django.core.management.base import SystemCheckError
from django.test import Client

from apps.people.models import Employee, Role
from conftest import activate_totp, totp_code
from tests.factories import PASSWORD, UserFactory

pytestmark = pytest.mark.django_db


def sign_in(client, email, password=PASSWORD):
    return client.post("/connexion/", {"login": email, "password": password})


def test_login_page_names_the_company(anonymous_client, company_a):
    content = anonymous_client(company_a.company).get("/connexion/").content.decode()
    assert "Espace Exemple SAS" in content
    assert 'for="id_login"' in content and 'for="id_password"' in content


def test_wrong_password_shows_one_explicit_error(anonymous_client, company_a):
    response = sign_in(anonymous_client(company_a.company), company_a.employee.email, "faux")
    content = response.content.decode()
    assert "incorrect" in content
    assert "informations sont à corriger" not in content


def test_anonymous_pages_redirect_to_login(anonymous_client, company_a):
    response = anonymous_client(company_a.company).get("/notifications/")
    assert response.status_code == 302
    assert response["Location"].startswith("/connexion/?next=")


def test_logout_closes_the_session(client_for, company_a):
    client = client_for(company_a.employee)
    assert client.post("/connexion/deconnexion/").status_code == 302
    assert client.get("/").status_code == 302


def test_left_employee_cannot_sign_in(anonymous_client, company_a):
    Employee.all_companies.filter(pk=company_a.employee.pk).update(status="left")
    client = anonymous_client(company_a.company)
    sign_in(client, company_a.employee.email)
    assert "_auth_user_id" not in client.session


def test_password_reset_only_mails_accounts_of_this_space(
    anonymous_client, company_a, company_b, run_tasks
):
    client = anonymous_client(company_a.company)
    response = client.post("/connexion/mot-de-passe/", {"email": company_b.employee.email})
    assert response.status_code == 302
    run_tasks()
    assert len(mail.outbox) == 0  # compte d'une autre entreprise : rien n'est envoyé
    client.post("/connexion/mot-de-passe/", {"email": company_a.employee.email})
    run_tasks()  # e-mails d'allauth par une tâche (L3-11)
    assert len(mail.outbox) == 1
    assert "exemple.localhost" in mail.outbox[0].body
    assert "/connexion/mot-de-passe/cle/" in mail.outbox[0].body


# ---------- Double authentification (T-10) ----------


def test_hr_must_enroll_on_first_login(anonymous_client, company_a, settings):
    settings.DEMO_DISABLE_2FA = False
    client = anonymous_client(company_a.company)
    response = sign_in(client, company_a.hr.email)
    assert response.status_code == 302
    for url in ["/", "/notifications/"]:
        response = client.get(url)
        assert response.status_code == 302
        assert response["Location"] == "/compte/securite/totp/activer/"
    page = client.get("/compte/securite/totp/activer/")
    assert page.status_code == 200
    assert "Activer la double authentification" in page.content.decode()


def test_enrolled_hr_needs_a_code_at_each_login(anonymous_client, company_a):
    secret = activate_totp(company_a.hr.user)
    client = anonymous_client(company_a.company)
    response = sign_in(client, company_a.hr.email)
    assert response["Location"] == "/connexion/2fa/"
    assert "_auth_user_id" not in client.session
    wrong = client.post("/connexion/2fa/", {"code": "000000"})
    assert wrong.status_code == 200 and "_auth_user_id" not in client.session
    client.post("/connexion/2fa/", {"code": totp_code(secret)})
    assert client.session["_auth_user_id"] == str(company_a.hr.user.pk)
    assert client.get("/").status_code == 200


def test_role_change_to_admin_forces_enrollment(client_for, company_a):
    client = client_for(company_a.employee)
    assert client.get("/").status_code == 200
    Employee.all_companies.filter(pk=company_a.employee.pk).update(role=Role.ADMIN)
    response = client.get("/")
    assert response["Location"] == "/compte/securite/totp/activer/"


def test_employees_do_not_need_two_factor(client_for, company_a):
    assert client_for(company_a.employee).get("/").status_code == 200


def test_demo_switch_only_works_in_development(client_for, company_a, settings):
    settings.DEMO_DISABLE_2FA = True
    settings.DEBUG = False
    client = client_for(company_a.hr, totp=False)
    assert client.get("/")["Location"] == "/compte/securite/totp/activer/"
    settings.DEBUG = True
    assert client.get("/").status_code == 200


def test_demo_switch_is_rejected_by_the_system_check(settings):
    settings.DEMO_DISABLE_2FA = True
    settings.DEBUG = False
    with pytest.raises(SystemCheckError):
        call_command("check")


# ---------- Hôte éditeur (T-22) ----------


def platform_client():
    return Client(HTTP_HOST="admin.localhost")


def test_platform_requires_sign_in(db):
    client = platform_client()
    response = client.get("/")
    assert response.status_code == 302
    # L'administration Django renvoie vers sa connexion, qui passe par allauth.
    response = client.get(response["Location"])
    assert response["Location"].startswith("/connexion/")


def test_client_accounts_cannot_sign_in_on_the_platform(company_a):
    client = platform_client()
    sign_in(client, company_a.admin.email)
    assert "_auth_user_id" not in client.session


def test_dianna_staff_has_no_rights_on_a_client_space(anonymous_client, company_a):
    staff = UserFactory(email="equipe@dianna.fr", is_staff=True, is_superuser=True)
    client = anonymous_client(company_a.company)
    sign_in(client, staff.email)
    assert "_auth_user_id" not in client.session


def test_dianna_staff_must_enroll_then_reaches_the_admin(db):
    staff = UserFactory(email="equipe@dianna.fr", is_staff=True, is_superuser=True)
    client = platform_client()
    client.force_login(staff, backend="apps.accounts.auth.HostAwareBackend")
    assert client.get("/")["Location"] == "/compte/securite/totp/activer/"
    activate_totp(staff)
    response = client.get("/")
    assert response.status_code == 200
    assert "Entreprises clientes" in response.content.decode()
