"""Tâches des questionnaires, exécutées par le travailleur (django-tasks-db)."""

from django.tasks import task
from django.utils import timezone


@task
def close_expired_surveys(company_id: int) -> int:
    """Clôt les questionnaires dont l'échéance est passée (L6-06), si le module est activé."""
    from apps.core.access import company_module_enabled
    from apps.core.models import Company, Module
    from apps.core.tenancy import tenant_context
    from apps.surveys import services

    company = Company.objects.filter(pk=company_id, status=Company.Status.ACTIVE).first()
    if company is None:
        return 0
    with tenant_context(company):
        if not company_module_enabled(Module.SURVEYS):
            return 0
        return services.close_expired(timezone.localdate())
