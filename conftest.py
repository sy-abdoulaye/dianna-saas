"""Fixtures communes : deux entreprises aux données équivalentes (tests d'isolation)."""

from dataclasses import dataclass

import pytest
from django.test import Client

from apps.core.tenancy import tenant_context
from apps.people.models import Role
from tests.factories import (
    AuditLogFactory,
    CompanyFactory,
    EmployeeFactory,
    NotificationFactory,
    ServiceFactory,
    SiteFactory,
    invitation_for,
)

BACKEND = "apps.accounts.auth.HostAwareBackend"


@dataclass
class CompanyData:
    company: object
    site: object
    service: object
    admin: object
    hr: object
    manager: object
    employee: object
    pending: object  # fiche sans compte, avec invitation
    invitation: object
    invitation_token: str
    notification: object
    audit: object


def build_company(slug: str, name: str) -> CompanyData:
    company = CompanyFactory(slug=slug, name=name)
    site = SiteFactory(company=company, name="Lyon")
    service = ServiceFactory(company=company, name="Support client")
    common = {"company": company, "site": site, "service": service}
    admin = EmployeeFactory(**common, first_name="Marc", last_name=f"Admin{slug}", role=Role.ADMIN)
    hr = EmployeeFactory(**common, first_name="Hélène", last_name=f"Rh{slug}", role=Role.HR)
    manager = EmployeeFactory(
        **common, first_name="Louise", last_name=f"Manager{slug}", role=Role.MANAGER
    )
    employee = EmployeeFactory(
        **common, first_name="Camille", last_name=f"Salarie{slug}", manager=manager
    )
    pending = EmployeeFactory(**common, first_name="Sofia", last_name=f"Nouvelle{slug}", user=None)
    invitation, token = invitation_for(pending)
    notification = NotificationFactory(company=company, recipient=employee)
    audit = AuditLogFactory(company=company, actor=admin)
    return CompanyData(
        company,
        site,
        service,
        admin,
        hr,
        manager,
        employee,
        pending,
        invitation,
        token,
        notification,
        audit,
    )


@pytest.fixture
def company_a(db):
    return build_company("exemple", "Exemple SAS")


@pytest.fixture
def company_b(db):
    return build_company("autre", "Autre SA")


@pytest.fixture
def in_company():
    """with in_company(company): … ouvre le contexte d'une entreprise dans un test."""
    return tenant_context


def host_for(company) -> str:
    return f"{company.slug}.localhost"


def activate_totp(user) -> str:
    """Inscrit un authentificateur TOTP ; renvoie le secret (pour calculer des codes)."""
    from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret

    secret = generate_totp_secret()
    TOTP.activate(user, secret)
    return secret


def totp_code(secret: str) -> str:
    from allauth.mfa.totp.internal.auth import (
        format_hotp_value,
        hotp_value,
        yield_hotp_counters_from_time,
    )

    counter = next(iter(yield_hotp_counters_from_time()))
    return format_hotp_value(hotp_value(secret, counter))


@pytest.fixture
def client_for():
    """Client connecté sur le sous-domaine de l'entreprise de la fiche. Les profils RH et
    Admin ont leur double authentification inscrite, sauf `totp=False`."""

    def _client(employee, *, totp=True):
        if totp and employee.requires_two_factor:
            from allauth.mfa.models import Authenticator

            if not Authenticator.objects.filter(user=employee.user).exists():
                activate_totp(employee.user)
        client = Client(HTTP_HOST=host_for(employee.company))
        client.force_login(employee.user, backend=BACKEND)
        return client

    return _client


@pytest.fixture
def anonymous_client():
    def _client(company):
        return Client(HTTP_HOST=host_for(company))

    return _client
