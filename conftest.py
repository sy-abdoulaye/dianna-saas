"""Fixtures communes : deux entreprises aux données équivalentes (tests d'isolation)."""

from dataclasses import dataclass

import pytest
from django.test import Client

from apps.core.context import ActionContext
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
    from apps.approvals.tests.conftest import free_monday

    monday = free_monday()
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
    from django.core.files.base import ContentFile

    from apps.agenda.models import Closure
    from apps.approvals.models import TransportProof

    closure = Closure.objects.create(date=date(2030, 12, 24), label="Fermeture de fin d'année")
    proof = TransportProof(
        requester=employee,
        month=date(2030, 1, 1),
        amount="84.10",
        file_type="application/pdf",
        original_name="abonnement.pdf",
        submitted_at=now,
    )
    proof.compute_validity()
    proof.file.save("justificatif.pdf", ContentFile(PDF_BYTES), save=False)
    proof.save()
    return {
        "telework": telework,
        "leave": leave,
        "on_call": on_call,
        "campaign": campaign,
        "event": event,
        "calendar": calendar,
        "closure": closure,
        "transport": proof,
        **build_equipment(employee, now),
    }


def build_equipment(employee, now) -> dict:
    """Un équipement attribué (avec son historique et un signalement), un autre en stock et
    une demande de matériel validée, sans attribution."""
    from apps.equipment.models import (
        EquipmentAssignment,
        EquipmentEvent,
        EquipmentIssue,
        EquipmentItem,
        EquipmentRequest,
    )

    held = EquipmentItem.objects.create(
        kind="laptop",
        model="Dell Latitude 5440",
        serial_number=f"DN-{employee.company.slug.upper()}-1",
        status="assigned",
        holder=employee,
        assigned_at=now,
    )
    stock = EquipmentItem.objects.create(
        kind="screen", model="Dell U2723QE", serial_number=f"DN-{employee.company.slug.upper()}-2"
    )
    assignment = EquipmentAssignment.objects.create(item=held, employee=employee, assigned_at=now)
    event = EquipmentEvent.objects.create(item=held, action="assigned", employee=employee)
    issue = EquipmentIssue.objects.create(
        item=held, reported_by=employee, description="Écran cassé"
    )
    equipment_request = EquipmentRequest.objects.create(
        requester=employee,
        kind="screen",
        reason="Deuxième écran",
        status="approved",
        submitted_at=now,
    )
    return {
        "item": held,
        "stock_item": stock,
        "assignment": assignment,
        "equipment_event": event,
        "issue": issue,
        "equipment_request": equipment_request,
    }


def build_communication(*, author, people, respondent) -> dict:
    """Lot 6 : une annonce lue par l'auteur ; un questionnaire ouvert (deux questions, public
    figé sur `people`, une réponse anonyme et son reçu) et un brouillon."""
    from django.utils import timezone

    from apps.announcements.models import Announcement, AnnouncementRead
    from apps.surveys.models import (
        Answer,
        Question,
        Survey,
        SurveyInvitation,
        SurveyReceipt,
        SurveyResponse,
    )

    now = timezone.now()
    announcement = Announcement.objects.create(
        title="Fermeture du site le 24 décembre",
        category="site_life",
        body="Le site sera fermé le jeudi 24 décembre.",
        author=author,
        published_at=now,
    )
    read = AnnouncementRead.objects.create(announcement=announcement, employee=author)
    survey = Survey.objects.create(
        title="Baromètre", status="open", created_by=author, published_at=now
    )
    question = Question.objects.create(
        survey=survey, order=1, kind="scale", label="Je me sens bien dans mon équipe."
    )
    Question.objects.create(survey=survey, order=2, kind="text", label="Une idée ?")
    invitations = [SurveyInvitation.objects.create(survey=survey, employee=p) for p in people]
    receipt = SurveyReceipt.objects.create(survey=survey, employee=respondent)
    response = SurveyResponse.objects.create(survey=survey)
    answer = Answer.objects.create(response=response, question=question, score=4)
    draft = Survey.objects.create(title="Formation 2027", created_by=author)
    Question.objects.create(survey=draft, order=1, kind="scale", label="Question du brouillon")
    return {
        "announcement": announcement,
        "announcement_read": read,
        "survey": survey,
        "draft_survey": draft,
        "question": question,
        "invitation": invitations[0],
        "receipt": receipt,
        "response": response,
        "answer": answer,
    }


def build_careers(*, employee, manager, hr) -> dict:
    """Lot 7 : compétences par défaut, une campagne, un entretien individuel à l'étape du
    manager (note et objectif), un entretien de parcours clos (formation), une note publique
    et une note privée du manager ; une intervention et un compte rendu envoyé (deux travaux,
    historique)."""
    from datetime import date

    from django.utils import timezone

    from apps.careers.models import (
        Competency,
        FollowUpNote,
        Review,
        ReviewCampaign,
        ReviewObjective,
        ReviewRating,
        ReviewTraining,
    )
    from apps.careers.services import create_default_competencies
    from apps.interventions.models import InterventionReport, Mission, ReportEvent, ReportItem

    create_default_competencies()
    competency = Competency.objects.order_by("order").first()
    today = timezone.localdate()
    campaign = ReviewCampaign.objects.create(
        label="Campagne de test",
        start=today.replace(month=1, day=1),
        end=today.replace(month=12, day=31),
    )
    review = Review.objects.create(
        employee=employee,
        manager=manager,
        launched_by=manager,
        kind="individual",
        step="manager",
        campaign=campaign,
        self_summary="Une année riche en projets et en apprentissages.",
    )
    rating = ReviewRating.objects.create(review=review, competency=competency, score=3)
    objective = ReviewObjective.objects.create(
        review=review, title="Former un nouvel arrivant", due_date=date(2031, 6, 30)
    )
    closed = Review.objects.create(
        employee=employee,
        manager=manager,
        kind="professional",
        reason="periodic",
        step="closed",
        closed_at=timezone.now(),
    )
    training = ReviewTraining.objects.create(review=closed, label="Animation de réunion")
    note = FollowUpNote.objects.create(
        employee=employee, author=manager, date=today, kind="follow_up", text="Point de suivi."
    )
    private_note = FollowUpNote.objects.create(
        employee=employee,
        author=manager,
        date=today,
        kind="follow_up",
        text="Note privée du manager.",
        is_private=True,
    )
    mission = Mission.objects.create(name="Support niveau 2 · contrat Atlas")
    report = InterventionReport.objects.create(
        employee=employee,
        mission=mission,
        period=today.replace(day=1),
        status="submitted",
        visibility="planned_end",
        planned_end=date(2031, 12, 31),
        submitted_at=timezone.now(),
    )
    item = ReportItem.objects.create(
        report=report, section="done", order=1, description="Tickets de niveau 2", completion=80
    )
    ReportItem.objects.create(
        report=report, section="next", order=1, description="Base de connaissances", completion=50
    )
    report_event = ReportEvent.objects.create(report=report, actor=employee, action="submitted")
    return {
        "competency": competency,
        "review_campaign": campaign,
        "review": review,
        "rating": rating,
        "objective": objective,
        "closed_review": closed,
        "training": training,
        "note": note,
        "private_note": private_note,
        "mission": mission,
        "report": report,
        "report_item": item,
        "report_event": report_event,
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
        requests.update(
            build_communication(
                author=hr, people=[admin, hr, manager, employee], respondent=employee
            )
        )
        requests.update(build_careers(employee=employee, manager=manager, hr=hr))
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
            return workflow.submit(model, data, context=ActionContext(employee))

    return _submit


@pytest.fixture(autouse=True)
def clear_cache():
    """Limites de fréquence (exports, vitrine) : chaque test part d'un cache vide."""
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


# Plus petit PDF valide utilisé par les tests (justificatifs).
PDF_BYTES = (
    b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>endobj\n"
    b"trailer<</Root 1 0 R>>\n%%EOF\n"
)


@pytest.fixture(autouse=True)
def private_files(settings, tmp_path):
    """Fichiers privés de chaque test dans un dossier temporaire, sur disque."""
    from django.utils.functional import empty

    from apps.core.files import private_storage, reset_circuit

    settings.PRIVATE_MEDIA_ROOT = tmp_path / "private"
    settings.PRIVATE_STORAGE_BACKEND = "filesystem"
    private_storage._wrapped = empty
    reset_circuit()
    yield
    private_storage._wrapped = empty
    reset_circuit()
