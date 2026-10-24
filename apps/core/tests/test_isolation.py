"""Batterie d'isolation entre entreprises (docs/02-architecture.md, section Tests)."""

import importlib

import pytest
from django.apps import apps
from django.core.exceptions import ValidationError
from django.test import Client
from django.urls import URLPattern, URLResolver, get_resolver

from apps.accounts.models import Invitation
from apps.agenda.models import CalendarEvent, Closure
from apps.announcements.models import Announcement, AnnouncementRead
from apps.approvals.models import (
    LeaveRequest,
    OnCallDeclaration,
    RequestEvent,
    SummerCampaign,
    TeleworkRequest,
    TransportProof,
)
from apps.core.models import (
    AuditLog,
    Company,
    CompanyModule,
    Notification,
    Service,
    Site,
    TenantBase,
    TenantManager,
    TenantModel,
)
from apps.core.tenancy import (
    CompanyMismatchError,
    NoCurrentCompanyError,
    current_company,
    tenant_context,
)
from apps.equipment.models import (
    EquipmentAssignment,
    EquipmentEvent,
    EquipmentIssue,
    EquipmentItem,
    EquipmentRequest,
)
from apps.people.models import Employee, EmployeeChange
from apps.surveys.models import (
    Answer,
    Question,
    Survey,
    SurveyInvitation,
    SurveyReceipt,
    SurveyResponse,
)
from tests.factories import PASSWORD, EmployeeFactory
from tests.isolation import ISOLATION_CASES, NOT_TENANT_OBJECTS

# Modèles sans entreprise, par construction.
NOT_TENANT_MODELS = {
    Company,
    apps.get_model("accounts", "User"),
    # Compteur technique de limite de fréquence : clé en empreinte HMAC, sans donnée métier.
    apps.get_model("core", "RateLimitCounter"),
}


def project_models():
    return [m for m in apps.get_models() if m.__module__.startswith("apps.")]


# ---------- Règle 1 : tout modèle métier hérite de TenantModel (ou TenantBase) ----------


def test_every_business_model_is_a_tenant_model():
    offenders = [
        m.__name__
        for m in project_models()
        if m not in NOT_TENANT_MODELS and not issubclass(m, TenantBase)
    ]
    assert offenders == []


def test_only_anonymous_survey_answers_have_no_timestamps():
    """TenantBase (sans horodatage) est réservée aux réponses anonymes (M-10) : tout autre
    modèle métier hérite de TenantModel."""
    untimed = {
        m for m in project_models() if issubclass(m, TenantBase) and not issubclass(m, TenantModel)
    }
    assert untimed == {SurveyResponse, Answer}


@pytest.mark.parametrize(
    "model", [m for m in project_models() if issubclass(m, TenantBase)], ids=lambda m: m.__name__
)
def test_tenant_models_filter_by_default_and_refuse_queries_without_company(model, db):
    assert isinstance(model._default_manager, TenantManager)
    assert not isinstance(model._base_manager, TenantManager)
    with pytest.raises(NoCurrentCompanyError):
        list(model.objects.all())
    for operation in ("count", "exists", "first", "delete"):
        with pytest.raises(NoCurrentCompanyError):
            getattr(model.objects.all(), operation)()
    with pytest.raises(NoCurrentCompanyError):
        model.objects.update(company=None)
    # Construire un queryset sans l'évaluer reste permis (champs de ModelForm à l'import).
    model.objects.filter(pk__gt=0)


QUERYSET_EVALUATIONS = {
    "list": lambda qs: list(qs),
    "count": lambda qs: qs.count(),
    "exists": lambda qs: qs.exists(),
    "first": lambda qs: qs.first(),
    "update": lambda qs: qs.update(updated_at=None),
    "subquery": lambda qs: list(Employee.objects.filter(pk__in=qs.values("pk"))),
}


@pytest.mark.parametrize("evaluate", QUERYSET_EVALUATIONS.values(), ids=QUERYSET_EVALUATIONS)
def test_queryset_built_in_a_and_evaluated_in_b_is_refused(evaluate, company_a, company_b):
    with tenant_context(company_a.company):
        built_in_a = Employee.objects.all()
    with tenant_context(company_b.company), pytest.raises(CompanyMismatchError):
        evaluate(built_in_a)


@pytest.mark.parametrize("evaluate", QUERYSET_EVALUATIONS.values(), ids=QUERYSET_EVALUATIONS)
def test_queryset_built_without_company_and_evaluated_in_a_is_refused(evaluate, company_a):
    built_without_company = Employee.objects.all()
    with tenant_context(company_a.company), pytest.raises(CompanyMismatchError):
        evaluate(built_without_company)


def test_queryset_clones_keep_their_company(company_a, company_b):
    with tenant_context(company_a.company):
        built_in_a = Employee.objects.filter(pk__gt=0)
        assert built_in_a.order_by("pk").all().exists()  # même entreprise : permis
    with tenant_context(company_b.company), pytest.raises(CompanyMismatchError):
        list(built_in_a.order_by("pk").all())


def model_form_class():
    from django import forms

    class ManagerForm(forms.ModelForm):
        class Meta:
            model = Employee
            fields = ["manager", "service"]

    return ManagerForm


def test_model_form_declared_outside_a_request_cannot_list_choices(company_a):
    form_class = model_form_class()  # comme à l'import : aucune entreprise courante
    with tenant_context(company_a.company):
        form = form_class()
        for name in ("manager", "service"):
            with pytest.raises(CompanyMismatchError):
                list(form.fields[name].queryset)


def test_model_form_declared_in_a_cannot_list_choices_in_b(company_a, company_b):
    with tenant_context(company_a.company):
        form_class = model_form_class()  # import pendant la première requête, entreprise A
    with tenant_context(company_b.company):
        form = form_class()
        with pytest.raises(CompanyMismatchError):
            list(form.fields["manager"].queryset)


def test_project_forms_list_the_current_company_only(company_a, company_b, client_for):
    with tenant_context(company_a.company):
        # Import pendant une requête de A (Gunicorn sans --preload).
        forms_module = importlib.reload(importlib.import_module("apps.people.forms"))
    with tenant_context(company_b.company):
        employee_form = forms_module.EmployeeForm()
        filter_form = forms_module.DirectoryFilterForm()
        for queryset in (
            employee_form.fields["manager"].queryset,
            employee_form.fields["service"].queryset,
            employee_form.fields["site"].queryset,
            filter_form.fields["service"].queryset,
            filter_form.fields["site"].queryset,
        ):
            assert {obj.company_id for obj in queryset} == {company_b.company.pk}
    # Et dans une vraie requête sur l'hôte de B : le formulaire ne propose que B.
    page = client_for(company_b.hr).get("/annuaire/nouveau/").content.decode()
    assert company_b.manager.last_name in page
    assert company_a.manager.last_name not in page


def test_project_imports_without_a_current_company():
    for module in ("apps.people.forms", "apps.administration.forms", "config.urls"):
        importlib.reload(importlib.import_module(module))


# ---------- Données : deux entreprises équivalentes ----------

TENANT_ROWS = {
    Site: lambda d: d.site,
    Service: lambda d: d.service,
    Employee: lambda d: d.employee,
    Notification: lambda d: d.notification,
    AuditLog: lambda d: d.audit,
    Invitation: lambda d: d.invitation,
    EmployeeChange: lambda d: d.change,
    TeleworkRequest: lambda d: d.requests["telework"],
    LeaveRequest: lambda d: d.requests["leave"],
    OnCallDeclaration: lambda d: d.requests["on_call"],
    SummerCampaign: lambda d: d.requests["campaign"],
    RequestEvent: lambda d: d.requests["event"],
    CalendarEvent: lambda d: d.requests["calendar"],
    Closure: lambda d: d.requests["closure"],
    TransportProof: lambda d: d.requests["transport"],
    EquipmentItem: lambda d: d.requests["item"],
    EquipmentAssignment: lambda d: d.requests["assignment"],
    EquipmentEvent: lambda d: d.requests["equipment_event"],
    EquipmentIssue: lambda d: d.requests["issue"],
    EquipmentRequest: lambda d: d.requests["equipment_request"],
    CompanyModule: lambda d: CompanyModule.all_companies.filter(company=d.company).first(),
    Announcement: lambda d: d.requests["announcement"],
    AnnouncementRead: lambda d: d.requests["announcement_read"],
    Survey: lambda d: d.requests["survey"],
    Question: lambda d: d.requests["question"],
    SurveyInvitation: lambda d: d.requests["invitation"],
    SurveyReceipt: lambda d: d.requests["receipt"],
    SurveyResponse: lambda d: d.requests["response"],
    Answer: lambda d: d.requests["answer"],
}


@pytest.mark.parametrize("model", TENANT_ROWS, ids=lambda m: m.__name__)
def test_queries_only_return_the_current_company(model, company_a, company_b):
    row_b = TENANT_ROWS[model](company_b)
    with tenant_context(company_a.company):
        companies = set(model.objects.values_list("company_id", flat=True))
        assert companies == {company_a.company.pk}
        with pytest.raises(model.DoesNotExist):
            model.objects.get(pk=row_b.pk)


def test_every_tenant_model_is_covered_by_the_data_battery():
    covered = set(TENANT_ROWS)
    tenant_models = {m for m in project_models() if issubclass(m, TenantBase)}
    assert tenant_models - covered == set()


def test_saving_an_object_of_another_company_is_refused(company_a, company_b):
    with tenant_context(company_a.company), pytest.raises(ValidationError):
        company_b.site.name = "Piraté"
        company_b.site.save()


def test_new_objects_take_the_current_company(company_a):
    with tenant_context(company_a.company):
        site = Site.objects.create(name="Nantes")
    assert site.company_id == company_a.company.pk


def test_creating_without_company_is_refused(db):
    with pytest.raises(NoCurrentCompanyError):
        Site(name="Orphelin").save()


@pytest.mark.parametrize("field", ["manager", "service", "site"])
def test_foreign_keys_must_stay_in_the_same_company(company_a, company_b, field):
    target = {
        "manager": company_b.manager,
        "service": company_b.service,
        "site": company_b.site,
    }[field]
    with tenant_context(company_a.company):
        employee = Employee.objects.get(pk=company_a.employee.pk)
        setattr(employee, field, target)
        with pytest.raises(ValidationError) as error:
            employee.save()
    assert field in error.value.message_dict


def test_unique_constraints_are_per_company(company_a, company_b):
    # Même nom de service et même e-mail de fiche dans deux entreprises : permis.
    assert company_a.service.name == company_b.service.name
    with tenant_context(company_b.company):
        EmployeeFactory(company=company_b.company, email=company_a.employee.email, user=None)


# ---------- Requêtes HTTP ----------


def test_context_is_reset_after_each_request(company_a, client_for):
    client_for(company_a.employee).get("/")
    assert current_company.get() is None


def test_unknown_subdomain_is_404(db):
    assert Client(HTTP_HOST="inconnue.localhost").get("/").status_code == 404


def test_suspended_company_shows_the_dedicated_page(company_a):
    Company.objects.filter(pk=company_a.company.pk).update(status=Company.Status.SUSPENDED)
    response = Client(HTTP_HOST="exemple.localhost").get("/connexion/")
    assert response.status_code == 503
    assert "Espace suspendu" in response.content.decode()


def test_a_session_does_not_work_on_another_company_host(company_a, company_b):
    client = Client(HTTP_HOST="exemple.localhost")
    client.force_login(company_a.employee.user, backend="apps.accounts.auth.HostAwareBackend")
    assert client.get("/").status_code == 200
    # Même cookie de session présenté sur l'hôte de B : la session est fermée.
    response = client.get("/", HTTP_HOST="autre.localhost")
    assert response.status_code == 302
    assert response["Location"].startswith("/connexion/")


def test_a_user_cannot_sign_in_on_another_company_host(company_a, company_b):
    client = Client(HTTP_HOST="autre.localhost")
    response = client.post(
        "/connexion/", {"login": company_a.employee.user.email, "password": PASSWORD}
    )
    assert response.status_code == 200  # formulaire réaffiché, aucune session
    assert "_auth_user_id" not in client.session


def test_the_right_user_signs_in_on_its_own_host(company_a):
    client = Client(HTTP_HOST="exemple.localhost")
    response = client.post(
        "/connexion/", {"login": company_a.employee.user.email, "password": PASSWORD}
    )
    assert response.status_code == 302
    assert client.session["_auth_user_id"] == str(company_a.employee.user.pk)


@pytest.mark.parametrize("route", sorted(ISOLATION_CASES))
def test_objects_of_another_company_are_404(route, company_a, company_b, client_for):
    method, build_url = ISOLATION_CASES[route]
    client = client_for(company_a.admin)
    response = getattr(client, method)(build_url(company_b))
    assert response.status_code == 404


def _routes(resolver, prefix=""):
    for pattern in resolver.url_patterns:
        if isinstance(pattern, URLResolver):
            ns = f"{prefix}{pattern.namespace}:" if pattern.namespace else prefix
            yield from _routes(pattern, ns)
        elif isinstance(pattern, URLPattern) and pattern.name:
            yield f"{prefix}{pattern.name}", pattern


def test_every_parameterized_route_is_registered():
    parameterized = {
        name
        for name, pattern in _routes(get_resolver("config.urls"))
        if pattern.pattern.regex.groups
    }
    missing = parameterized - set(ISOLATION_CASES) - NOT_TENANT_OBJECTS
    assert missing == set(), "Ajoutez ces routes à tests/isolation.py"


def test_a_service_in_use_cannot_be_deleted_but_the_company_can(company_a):
    from django.db.models import RestrictedError

    with tenant_context(company_a.company), pytest.raises(RestrictedError):
        Service.objects.get(pk=company_a.service.pk).delete()
    Company.objects.filter(pk=company_a.company.pk).delete()
    assert not Employee.all_companies.filter(company_id=company_a.company.pk).exists()
