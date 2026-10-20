"""Parcours du socle (lot 1) : vitrine, connexion par profil, double authentification,
isolation entre entreprises (parcours 8 de docs/08-prompts-claude-code.md), thème, cloche,
invitation."""

import re

import pytest
from playwright.sync_api import Page, expect

from conftest import activate_totp, totp_code
from tests.factories import PASSWORD

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def urls(live_server):
    port = live_server.url.rsplit(":", 1)[1]

    def _url(host: str, path: str = "/") -> str:
        prefix = f"{host}." if host else ""
        return f"http://{prefix}localhost:{port}{path}"

    return _url


def sign_in(page: Page, url: str, email: str, password: str = PASSWORD):
    page.goto(url)
    page.get_by_label("E-mail").fill(email)
    page.get_by_label("Mot de passe").fill(password)
    page.get_by_role("button", name="Se connecter").click()


def test_public_page_sends_the_link_by_email(page, urls, company_a, run_tasks):
    from django.core import mail

    page.goto(urls("", "/"))
    page.get_by_label("Adresse e-mail professionnelle").fill(company_a.employee.email)
    page.get_by_role("button", name="Recevoir le lien").click()
    expect(page.get_by_text("vous allez recevoir un lien de connexion")).to_be_visible()
    run_tasks()  # l'e-mail part par le travailleur de tâches (L3-01)
    link = next(line for line in mail.outbox[-1].body.splitlines() if "/connexion/" in line)
    page.goto(link.strip())
    expect(page.get_by_text("Espace Exemple SAS")).to_be_visible()


@pytest.mark.parametrize(("who", "profile"), [("employee", "Salarié"), ("manager", "Manager")])
def test_profiles_without_two_factor_sign_in(page, urls, company_a, who, profile):
    person = getattr(company_a, who)
    sign_in(page, urls("exemple", "/connexion/"), person.email)
    expect(page.get_by_role("heading", level=1)).to_have_text(f"Bonjour {person.first_name}")
    expect(page.get_by_text(f"{profile} · Exemple SAS")).to_be_visible()


@pytest.mark.parametrize(
    ("who", "profile"), [("hr", "Ressources humaines"), ("admin", "Administrateur")]
)
def test_hr_and_admin_sign_in_with_a_code(page, urls, company_a, who, profile):
    person = getattr(company_a, who)
    secret = activate_totp(person.user)
    sign_in(page, urls("exemple", "/connexion/"), person.email)
    expect(page.get_by_role("heading", name="Double authentification")).to_be_visible()
    page.get_by_label("Code").fill(totp_code(secret))
    page.get_by_role("button", name="Valider").click()
    expect(page.get_by_text(f"{profile} · Exemple SAS")).to_be_visible()


def test_first_login_of_hr_requires_enrollment(page, urls, company_a):
    sign_in(page, urls("exemple", "/connexion/"), company_a.hr.email)
    expect(page.get_by_role("heading", name="Activer la double authentification")).to_be_visible()
    page.goto(urls("exemple", "/notifications/"))
    expect(page).to_have_url(re.compile(r"/compte/securite/totp/activer/"))


def test_users_of_another_company_see_nothing_of_exemple(page, urls, company_a, company_b):
    # Parcours 8 : un utilisateur d'Autre SA ne peut ouvrir aucune URL d'Exemple SAS.
    sign_in(page, urls("autre", "/connexion/"), company_b.employee.email)
    expect(page.get_by_text("Salarié · Autre SA")).to_be_visible()
    page.goto(urls("exemple", f"/notifications/{company_a.notification.pk}/ouvrir/"))
    expect(page).to_have_url(re.compile(r"exemple\.localhost:\d+/connexion/"))
    sign_in(page, urls("exemple", "/connexion/"), company_b.employee.email)
    expect(page.get_by_role("alert")).to_contain_text("incorrect")
    page.goto(urls("autre", f"/notifications/{company_a.notification.pk}/ouvrir/"))
    expect(page.get_by_role("heading", name="Page introuvable")).to_be_visible()


def test_theme_follows_the_account_on_a_new_device(browser, urls, company_a):
    first = browser.new_context()
    page = first.new_page()
    sign_in(page, urls("exemple", "/connexion/"), company_a.employee.email)
    page.get_by_role("button", name=company_a.employee.full_name).click()
    with page.expect_response(re.compile(r"/compte/theme/")):
        page.locator("#menu-user").get_by_label("Sombre").check()
    first.close()
    second = browser.new_context()
    page = second.new_page()
    sign_in(page, urls("exemple", "/connexion/"), company_a.employee.email)
    expect(page.locator("html")).to_have_attribute("data-theme", "dark")
    second.close()


def test_bell_marks_notifications_as_read(page, urls, company_a):
    sign_in(page, urls("exemple", "/connexion/"), company_a.employee.email)
    bell = page.get_by_role("button", name="Notifications, 1 non lue")
    bell.click()
    page.get_by_role("link", name=company_a.notification.text).click()
    expect(page.get_by_role("button", name="Notifications", exact=True)).to_be_visible()


def test_invitation_creates_the_password_and_signs_in(page, urls, company_a):
    page.goto(urls("exemple", f"/invitation/{company_a.invitation_token}/"))
    expect(page.get_by_text(company_a.pending.email)).to_be_visible()
    page.locator("#id_password1").fill("Une-phrase-de-passe-2026")
    page.get_by_label("Confirmer le mot de passe").fill("Une-phrase-de-passe-2026")
    page.get_by_role("button", name="Créer mon mot de passe").click()
    expect(page.get_by_role("heading", level=1)).to_have_text(
        f"Bonjour {company_a.pending.first_name}"
    )


def test_platform_admin_signs_in_with_a_code_without_csp_errors(page, urls, db, console_errors):
    from tests.factories import UserFactory

    staff = UserFactory(email="equipe@dianna.fr", is_staff=True, is_superuser=True)
    secret = activate_totp(staff)
    page.goto(urls("admin", "/"))
    expect(page).to_have_url(re.compile(r"admin\.localhost:\d+/connexion/"))
    page.get_by_label("E-mail").fill(staff.email)
    page.get_by_label("Mot de passe").fill(PASSWORD)
    page.get_by_role("button", name="Se connecter").click()
    page.get_by_label("Code").fill(totp_code(secret))
    page.get_by_role("button", name="Valider").click()
    expect(page.get_by_text("Entreprises clientes")).to_be_visible()
    page.goto(urls("admin", "/core/company/add/"))
    expect(page.get_by_label("Prénom du premier administrateur")).to_be_visible()
    assert console_errors == []
