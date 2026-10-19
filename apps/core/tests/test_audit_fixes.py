"""Corrections de l'audit du lot 1 (points 5a à 5g), chacune avec son test."""

import importlib
import sys

import pytest
from allauth.account.forms import default_token_generator
from allauth.account.utils import user_pk_to_url_str
from allauth.mfa.models import Authenticator
from django.contrib import admin
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.db import transaction
from django.test import Client

from apps.accounts.models import User
from apps.core import permissions
from apps.core.checks import mfa_encryption_key
from apps.core.models import Company, CompanyModule, Site
from apps.core.tenancy import tenant_context
from conftest import activate_totp
from tests.factories import SiteFactory, UserFactory
from tests.tenancy_app.models import Badge, Owned, Tag, Undeclared

pytestmark = pytest.mark.django_db


# ---------- a. Administration éditeur : aucun modèle de données clients ----------


def test_platform_admin_only_registers_companies_and_staff_accounts():
    registered = {model._meta.label for model in admin.site._registry}
    assert registered == {"core.Company", "accounts.User"}
    company_admin = admin.site._registry[Company]
    inlines = company_admin.get_inlines(None, Company(name="x", slug="x"))
    assert [inline.model for inline in inlines] == [CompanyModule]


# ---------- b. Secrets de double authentification chiffrés ----------


def test_totp_secret_is_encrypted_at_rest(company_a):
    secret = activate_totp(company_a.hr.user)
    stored = Authenticator.objects.get(user=company_a.hr.user).data["secret"]
    assert secret not in stored
    from apps.accounts.mfa import EncryptingMFAAdapter

    assert EncryptingMFAAdapter().decrypt(stored) == secret


def test_key_rotation_keeps_old_secrets_readable(settings):
    from cryptography.fernet import Fernet

    from apps.accounts.mfa import EncryptingMFAAdapter

    old, new = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    settings.MFA_ENCRYPTION_KEY = old
    token = EncryptingMFAAdapter().encrypt("secret-totp")
    settings.MFA_ENCRYPTION_KEY = f"{new},{old}"
    assert EncryptingMFAAdapter().decrypt(token) == "secret-totp"


@pytest.mark.parametrize(
    ("value", "error_id"),
    [("", "dianna.E002"), ("pas-une-cle", "dianna.E004"), ("__SECRET__", "dianna.E003")],
)
def test_encryption_key_is_checked(settings, value, error_id):
    settings.MFA_ENCRYPTION_KEY = settings.SECRET_KEY if value == "__SECRET__" else value
    assert error_id in {error.id for error in mfa_encryption_key(None)}


def test_production_requires_the_encryption_key_and_host_cookies(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "x" * 60)
    monkeypatch.setenv("ALLOWED_HOSTS", "dianna.fr")
    monkeypatch.delenv("MFA_ENCRYPTION_KEY", raising=False)
    sys.modules.pop("config.settings.prod", None)
    with pytest.raises(ImproperlyConfigured):
        importlib.import_module("config.settings.prod")
    sys.modules.pop("config.settings.prod", None)
    monkeypatch.setenv("MFA_ENCRYPTION_KEY", "cle")
    prod = importlib.import_module("config.settings.prod")
    sys.modules.pop("config.settings.prod", None)
    # g. Cookies __Host- : sans Domain, Path=/, Secure.
    assert prod.SESSION_COOKIE_NAME == "__Host-sessionid"
    assert prod.CSRF_COOKIE_NAME == "__Host-csrftoken"
    assert prod.SESSION_COOKIE_DOMAIN is None and prod.CSRF_COOKIE_DOMAIN is None
    assert prod.SESSION_COOKIE_PATH == "/" and prod.CSRF_COOKIE_PATH == "/"
    assert prod.SESSION_COOKIE_SECURE and prod.CSRF_COOKIE_SECURE


# ---------- c. Pas de suppression d'entreprise ----------


def test_companies_cannot_be_deleted_from_the_platform(company_a):
    staff = UserFactory(email="equipe@dianna.fr", is_staff=True, is_superuser=True)
    activate_totp(staff)
    client = Client(HTTP_HOST="admin.localhost")
    client.force_login(staff, backend="apps.accounts.auth.HostAwareBackend")
    assert client.get(f"/core/company/{company_a.company.pk}/delete/").status_code == 403
    changelist = client.get("/core/company/").content.decode()
    assert "delete_selected" not in changelist
    assert Company.objects.filter(pk=company_a.company.pk).exists()


# ---------- d. Un-à-un et plusieurs-à-plusieurs dans la même entreprise ----------


def test_one_to_one_to_another_company_is_refused(company_a, company_b):
    with tenant_context(company_a.company), pytest.raises(ValidationError):
        Badge.objects.create(site=company_b.site)


def test_many_to_many_to_another_company_is_refused(company_a, company_b):
    with tenant_context(company_b.company):
        tag_b = Tag.objects.create(name="B")
        badge_b = Badge.objects.create()
    with tenant_context(company_a.company):
        badge = Badge.objects.create(site=SiteFactory(company=company_a.company))
        tag_a = Tag.objects.create(name="A")
        badge.tags.add(tag_a)
        with pytest.raises(ValidationError), transaction.atomic():
            badge.tags.add(tag_b)
        with pytest.raises(ValidationError), transaction.atomic():
            tag_a.badges.add(badge_b)  # sens inverse
        assert list(badge.tags.values_list("name", flat=True)) == ["A"]


# ---------- e. Propriétaire déclaré explicitement ----------


def test_owner_is_the_declared_field_even_with_employee_and_author(company_a):
    obj = Owned(employee=company_a.employee, author=company_a.manager)
    obj.company = company_a.company
    assert permissions.owner_of(obj) == company_a.manager
    # Camille est la salariée de l'objet mais pas son autrice : pas de droit « Soi ».
    assert not permissions.can(company_a.employee, "interventions.view", obj)
    assert permissions.can(company_a.manager, "interventions.view", obj)


def test_empty_owner_refuses_access_instead_of_crashing(company_a):
    obj = Owned(employee=company_a.employee, author=None)
    obj.company = company_a.company
    assert permissions.can(company_a.hr, "interventions.view", obj) is False


def test_undeclared_owner_is_a_programming_error(company_a):
    obj = Undeclared(employee=company_a.employee)
    obj.company = company_a.company
    with pytest.raises(ImproperlyConfigured):
        permissions.can(company_a.hr, "interventions.view", obj)


def test_scope_queryset_uses_the_declared_owner(company_a):
    with tenant_context(company_a.company):
        Owned.objects.create(employee=company_a.manager, author=company_a.employee)
        Owned.objects.create(employee=company_a.employee, author=company_a.manager)
        mine = permissions.scope_queryset(
            company_a.employee, Owned.objects.all(), "interventions.view"
        )
        assert [o.author_id for o in mine] == [company_a.employee.pk]


# ---------- f. Clé de réinitialisation liée à l'hôte du compte ----------


def reset_path(user):
    key = default_token_generator.make_token(user)
    return f"/connexion/mot-de-passe/cle/{user_pk_to_url_str(user)}-{key}/"


def test_reset_key_is_refused_on_another_host(company_a, company_b):
    user = company_a.employee.user
    path = reset_path(user)
    other = Client(HTTP_HOST="autre.localhost").get(path)
    assert other.status_code == 200 and "Lien expiré" in other.content.decode()
    platform = Client(HTTP_HOST="admin.localhost").get(path)
    assert "Lien expiré" in platform.content.decode()
    own = Client(HTTP_HOST="exemple.localhost").get(path)
    assert own.status_code == 302  # clé valide : redirection vers le formulaire


def test_reset_key_of_dianna_staff_only_works_on_the_platform(company_a):
    staff = UserFactory(email="equipe@dianna.fr", is_staff=True)
    path = reset_path(staff)
    assert "Lien expiré" in Client(HTTP_HOST="exemple.localhost").get(path).content.decode()
    assert Client(HTTP_HOST="admin.localhost").get(path).status_code == 302


def test_reset_password_form_keeps_working_on_the_right_host(company_a):
    client = Client(HTTP_HOST="exemple.localhost")
    response = client.get(reset_path(company_a.employee.user))
    form_url = response["Location"]
    new = "Une-nouvelle-phrase-de-passe"
    client.post(form_url, {"password1": new, "password2": new})
    assert User.objects.get(pk=company_a.employee.user_id).check_password(new)


def test_site_model_is_still_isolated(company_a):
    with tenant_context(company_a.company):
        assert Site.objects.count() >= 1
