"""Cloche, notifications, menu, vitrine, administration éditeur, données de démonstration."""

import pytest
from django.core import mail
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client

from apps.core.models import AuditLog, Company, CompanyModule, Module, Notification
from apps.core.tenancy import tenant_context
from apps.people.models import Employee
from conftest import activate_totp
from tests.factories import NotificationFactory, UserFactory

pytestmark = pytest.mark.django_db


# ---------- Notifications ----------


def test_bell_shows_only_the_signed_in_user_notifications(client_for, company_a):
    NotificationFactory(company=company_a.company, recipient=company_a.manager, text="Pour Louise")
    content = client_for(company_a.employee).get("/").content.decode()
    assert company_a.notification.text in content
    assert "Pour Louise" not in content
    assert "Notifications, 1 non lue" in content


def test_opening_marks_as_read_and_follows_the_link(client_for, company_a):
    client = client_for(company_a.employee)
    response = client.get(f"/notifications/{company_a.notification.pk}/ouvrir/")
    assert response.status_code == 302 and response["Location"] == "/"
    assert Notification.all_companies.get(pk=company_a.notification.pk).read_at is not None


def test_a_colleague_notification_is_404(client_for, company_a):
    client = client_for(company_a.manager)
    assert client.get(f"/notifications/{company_a.notification.pk}/ouvrir/").status_code == 404


def test_external_links_are_never_followed(client_for, company_a):
    note = NotificationFactory(company=company_a.company, recipient=company_a.employee, url="/")
    Notification.all_companies.filter(pk=note.pk).update(url="//pirate.example")
    response = client_for(company_a.employee).get(f"/notifications/{note.pk}/ouvrir/")
    assert response["Location"] == "/"


def test_mark_all_as_read(client_for, company_a):
    client = client_for(company_a.employee)
    response = client.post("/notifications/tout-lire/", headers={"HX-Request": "true"})
    assert response.status_code == 200
    assert "Aucune notification" not in response.content.decode()  # liste conservée, lue
    assert not Notification.all_companies.filter(
        recipient=company_a.employee, read_at__isnull=True
    ).exists()


def test_notifications_page_lists_and_paginates(client_for, company_a):
    content = client_for(company_a.employee).get("/notifications/").content.decode()
    assert company_a.notification.text in content


def test_notify_refuses_external_urls(company_a):
    from apps.core import notifications

    with tenant_context(company_a.company), pytest.raises(ValueError):
        notifications.notify(company_a.employee, "x", url="https://pirate.example")


# ---------- Menu ----------


def test_disabled_module_disappears_from_the_menu_for_everyone(company_a):
    from apps.core.navigation import build_nav

    modules = set(Module.values)
    assert any(i.key == "workload" for g in build_nav(company_a.employee, modules) for i in g.items)
    soon = [i for g in build_nav(company_a.employee, modules) for i in g.items if i.soon]
    assert all(i.url is None for i in soon)


def test_soon_entries_are_visible_but_not_clickable(client_for, company_a):
    content = client_for(company_a.employee).get("/").content.decode()
    assert "Plan de charge" in content
    assert 'title="Disponible dans une prochaine version"' in content
    assert "Recrutement" not in content  # profil sans équipe
    assert "Recrutement" in client_for(company_a.manager).get("/").content.decode()


def test_dashboard_greets_the_user(client_for, company_a):
    content = client_for(company_a.employee).get("/").content.decode()
    assert "Bonjour Camille" in content
    assert "Salarié · Exemple SAS" in content


# Vitrine : apps/core/tests/test_public.py


# ---------- Administration éditeur (T-22) ----------


@pytest.fixture
def staff_client(db):
    staff = UserFactory(email="equipe@dianna.fr", is_staff=True, is_superuser=True)
    activate_totp(staff)
    client = Client(HTTP_HOST="admin.localhost")
    client.force_login(staff, backend="apps.accounts.auth.HostAwareBackend")
    return client


def test_admin_creates_a_company_and_invites_its_first_admin(staff_client, run_tasks):
    response = staff_client.post(
        "/core/company/add/",
        {
            "name": "Nouvelle SARL",
            "slug": "nouvelle",
            "admin_first_name": "Ada",
            "admin_last_name": "Lovelace",
            "admin_email": "ada@nouvelle.fr",
        },
    )
    assert response.status_code == 302
    company = Company.objects.get(slug="nouvelle")
    assert CompanyModule.all_companies.filter(company=company).count() == len(Module.values)
    admin = Employee.all_companies.get(company=company)
    assert admin.role == "admin" and admin.user is None
    run_tasks()
    assert mail.outbox[-1].to == ["ada@nouvelle.fr"]
    assert "http://nouvelle.localhost/invitation/" in mail.outbox[-1].body


def test_admin_refuses_reserved_subdomains(staff_client):
    response = staff_client.post(
        "/core/company/add/",
        {
            "name": "X",
            "slug": "admin",
            "admin_first_name": "A",
            "admin_last_name": "B",
            "admin_email": "a@b.fr",
        },
    )
    assert response.status_code == 200
    assert "Ce sous-domaine est réservé." in response.content.decode()


def test_admin_toggles_modules_and_logs_it(staff_client, company_a):
    from apps.core import services

    services.set_module(company_a.company, Module.TELEWORK, False)
    with tenant_context(company_a.company):
        assert AuditLog.objects.filter(action="company.module_disabled").exists()
        assert not CompanyModule.objects.get(module=Module.TELEWORK).enabled
    page = staff_client.get(f"/core/company/{company_a.company.pk}/change/")
    assert page.status_code == 200


def test_admin_lists_only_dianna_staff_accounts(staff_client, company_a):
    content = staff_client.get("/accounts/user/").content.decode()
    assert "equipe@dianna.fr" in content
    assert company_a.employee.email not in content


# ---------- Données de démonstration ----------


def test_seed_demo_is_refused_outside_development(settings):
    settings.DEBUG = False
    with pytest.raises(CommandError):
        call_command("seed_demo")


def test_seed_demo_loads_both_companies(settings, db):
    settings.DEBUG = True
    call_command("seed_demo")
    exemple = Company.objects.get(slug="exemple")
    autre = Company.objects.get(slug="autre")
    assert Employee.all_companies.filter(company=exemple).count() == 24
    assert Employee.all_companies.filter(company=autre).count() == 4
    louise = Employee.all_companies.get(company=exemple, email="louise.martin@exemple.fr")
    assert louise.has_reports
    # Prototype : 5 collaborateurs directs (07-donnees-de-demo.md annonce « équipe de 6 »).
    assert Employee.all_companies.filter(manager=louise).count() == 5
    accounts = Employee.all_companies.filter(user__isnull=False).values_list("email", flat=True)
    assert set(accounts) == {
        "camille.durand@exemple.fr",
        "louise.martin@exemple.fr",
        "helene.faure@exemple.fr",
        "marc.diallo@exemple.fr",
        "nadia.berger@autre.fr",
    }
    with pytest.raises(CommandError):
        call_command("seed_demo")
    call_command("seed_demo", "--reset")
    assert Company.objects.filter(slug="exemple").count() == 1
