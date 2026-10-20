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
    change: object
    requests: dict


def build_requests(employee) -> dict:
    """Une demande de chaque type, avec son historique et son événement de calendrier,
    créées sans le moteur (données de la batterie d'isolation)."""
    from datetime import date, timedelta

    from django.utils import timezone

    from apps.agenda.models import CalendarEvent
    from apps.approvals.models import (
        LeaveRequest,
        OnCallDeclaration,
        RequestEvent,
        SummerCampaign,
        TeleworkRequest,
    )

    monday = timezone.localdate() + timedelta(days=7 - timezone.localdate().weekday())
    now = timezone.now()
    campaign = SummerCampaign.objects.create(
        label="Été 2027",
        period_start=date(2027, 6, 1),
        period_end=date(2027, 9, 30),
        deadline=date(2027, 2, 28),
        status=SummerCampaign.Status.OPEN,
    )
    telework = TeleworkRequest.objects.create(requester=employee, date=monday, submitted_at=now)
    leave = LeaveRequest.objects.create(
        requester=employee,
        campaign=campaign,
        start=date(2027, 7, 5),
        end=date(2027, 7, 16),
        submitted_at=now,
    )
    on_call = OnCallDeclaration.objects.create(
        requester=employee, start=monday, end=monday + timedelta(days=6), submitted_at=now
    )
    event = RequestEvent.objects.create(
        request_type="telework", request_id=telework.pk, actor=employee, action="submitted"
    )
    calendar = CalendarEvent.objects.create(
        employee=employee,
        kind="telework",
        start=monday,
        end=monday,
        source_type="telework",
        source_id=telework.pk,
    )
    return {
        "telework": telework,
        "leave": leave,
        "on_call": on_call,
        "campaign": campaign,
        "event": event,
        "calendar": calendar,
    }


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
    with tenant_context(company):
        from apps.people.models import EmployeeChange

        change = EmployeeChange.objects.create(employee=employee, actor=admin)
        requests = build_requests(employee)
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
        change,
        requests,
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


@pytest.fixture
def run_tasks():
    """Exécute les tâches en attente avec le vrai travailleur (`db_worker --batch`).
    `after_seconds` simule le temps écoulé (e-mails différés de 45 s). Dans un test, la
    connexion porte la transaction du test : le travailleur ne doit pas la fermer."""
    from datetime import timedelta

    from django.core.management import call_command
    from django.utils import timezone

    def _run(*, after_seconds: int = 0):
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(
                "django_tasks_db.management.commands.db_worker.close_old_connections",
                lambda: None,
            )
            if after_seconds:
                real_now = timezone.now
                patch.setattr(
                    timezone, "now", lambda: real_now() + timedelta(seconds=after_seconds)
                )
            call_command("db_worker", "--batch", "--no-startup-delay", verbosity=0)

    return _run


@pytest.fixture
def submit():
    """submit(company_data, employee, model, **data) : envoie une demande par le service,
    avec ses contrôles métier (RequestValidationError si l'un échoue). Les congés d'été sont
    rattachés par le service à la campagne ouverte, comme à l'écran."""
    from datetime import timedelta

    from apps.approvals import workflow
    from apps.approvals.models import LeaveRequest, OnCallDeclaration, TeleworkRequest
    from apps.approvals.tests.conftest import next_weekday

    def _submit(company_data, employee, model=TeleworkRequest, **data):
        if model is TeleworkRequest:
            data.setdefault("date", next_weekday(weekday=2))
        if model is LeaveRequest:
            data.setdefault(
                "start", company_data.requests["campaign"].period_start + timedelta(days=60)
            )
            data.setdefault("end", data["start"] + timedelta(days=9))
            data.setdefault("leave_type", LeaveRequest.LeaveType.SUMMER)
        if model is OnCallDeclaration:
            data.setdefault("start", next_weekday(offset_days=21))
            data.setdefault("end", data["start"] + timedelta(days=6))
        with tenant_context(company_data.company):
            return workflow.submit(model, employee, data)

    return _submit
