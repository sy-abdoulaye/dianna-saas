"""Fabriques de test. Les objets métier reçoivent leur entreprise explicitement (all_companies
n'est jamais nécessaire : `company=` est posé avant save, sans contexte courant)."""

import factory
from django.utils import timezone

from apps.accounts.models import User
from apps.core.models import AuditLog, Company, CompanyModule, Module, Notification, Service, Site
from apps.people.models import Employee, Role

PASSWORD = "mot-de-passe-de-test"


def ascii_slug(value: str) -> str:
    import unicodedata

    value = unicodedata.normalize("NFD", value).encode("ascii", "ignore").decode()
    return "".join(c for c in value.lower() if c.isalnum())


class CompanyFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Company
        django_get_or_create = ("slug",)
        skip_postgeneration_save = True

    name = factory.Sequence(lambda n: f"Entreprise {n}")
    slug = factory.Sequence(lambda n: f"entreprise{n}")

    @factory.post_generation
    def modules(self, create, extracted, **kwargs):
        if create:
            CompanyModule.all_companies.bulk_create(
                [CompanyModule(company=self, module=m) for m in Module.values],
                ignore_conflicts=True,
            )


class TenantFactory(factory.django.DjangoModelFactory):
    class Meta:
        abstract = True

    company = factory.SubFactory(CompanyFactory)

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        company = kwargs.pop("company")
        obj = model_class(*args, **kwargs)
        obj.company = company
        obj.save()
        return obj


class SiteFactory(TenantFactory):
    class Meta:
        model = Site

    name = factory.Sequence(lambda n: f"Site {n}")


class ServiceFactory(TenantFactory):
    class Meta:
        model = Service

    name = factory.Sequence(lambda n: f"Service {n}")


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User
        skip_postgeneration_save = True

    email = factory.Sequence(lambda n: f"compte{n}@exemple.fr")
    password = factory.PostGenerationMethodCall("set_password", PASSWORD)

    @classmethod
    def _after_postgeneration(cls, instance, create, results=None):
        if create:
            instance.save()


class EmployeeFactory(TenantFactory):
    class Meta:
        model = Employee

    first_name = factory.Sequence(lambda n: f"Prénom{n}")
    last_name = factory.Sequence(lambda n: f"Nom{n}")
    email = factory.LazyAttribute(
        lambda o: f"{ascii_slug(o.first_name)}.{ascii_slug(o.last_name)}@exemple.fr"
    )
    job_title = "Conseiller"
    role = Role.EMPLOYEE
    service = factory.LazyAttribute(lambda o: ServiceFactory(company=o.company))
    site = factory.LazyAttribute(lambda o: SiteFactory(company=o.company))
    user = factory.LazyAttribute(lambda o: UserFactory(email=o.email))


class NotificationFactory(TenantFactory):
    class Meta:
        model = Notification

    recipient = factory.LazyAttribute(lambda o: EmployeeFactory(company=o.company))
    text = "Votre demande a été validée."
    url = "/"


class AuditLogFactory(TenantFactory):
    class Meta:
        model = AuditLog

    action = "test.action"
    summary = "Action de test"


def invitation_for(employee, *, days=7):
    import hashlib
    import secrets
    from datetime import timedelta

    from apps.accounts.models import Invitation

    token = secrets.token_urlsafe(16)
    invitation = Invitation(
        employee=employee,
        token_hash=hashlib.sha256(token.encode()).hexdigest(),
        expires_at=timezone.now() + timedelta(days=days),
    )
    invitation.company = employee.company
    invitation.save()
    return invitation, token
