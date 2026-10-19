"""Opérations de plateforme (équipe Dianna) : création d'entreprise, modules."""

from django.db import transaction
from django.utils.translation import gettext as _

from apps.core import audit
from apps.core.models import Company, CompanyModule, Module
from apps.core.tenancy import tenant_context


@transaction.atomic
def create_company(
    *,
    name: str,
    slug: str,
    admin_first_name: str,
    admin_last_name: str,
    admin_email: str,
    invite: bool = True,
    request=None,
):
    """Crée l'entreprise, active tous les modules, crée la fiche du premier administrateur et
    lui envoie son invitation. Renvoie (company, employee, jeton d'invitation ou None)."""
    from apps.accounts import services as accounts
    from apps.people.models import Employee, Role

    company = Company(name=name, slug=slug)
    company.full_clean()
    company.save()
    with tenant_context(company):
        CompanyModule.objects.bulk_create(
            [CompanyModule(company=company, module=m, enabled=True) for m in Module.values]
        )
        admin = Employee.objects.create(
            first_name=admin_first_name,
            last_name=admin_last_name,
            email=admin_email,
            role=Role.ADMIN,
            job_title=_("Administrateur"),
        )
        audit.log(
            "platform.company_created",
            _("Espace créé par l'équipe Dianna"),
            target=company,
            request=request,
        )
        token = None
        if invite:
            _invitation, token = accounts.invite(admin, request=request)
    return company, admin, token


def set_module(company: Company, module: str, enabled: bool, *, actor=None, request=None):
    with tenant_context(company):
        row, _created = CompanyModule.objects.get_or_create(module=module)
        if row.enabled == enabled:
            return row
        row.enabled = enabled
        row.save(update_fields=["enabled", "updated_at"])
        label = Module(module).label
        audit.log(
            "company.module_enabled" if enabled else "company.module_disabled",
            (_("Module activé : %(m)s") if enabled else _("Module désactivé : %(m)s"))
            % {"m": label},
            actor=actor,
            request=request,
        )
        return row
