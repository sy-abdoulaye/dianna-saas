"""Entreprise courante (T-07, docs/02-architecture.md).

L'entreprise de la requête est posée par CompanyMiddleware dans une ContextVar, remise à
zéro à la fin de chaque requête. Les tâches et les commandes ouvrent le contexte avec
`with tenant_context(company):`. Sans entreprise courante, TenantManager lève
NoCurrentCompanyError : aucune requête métier ne peut partir sans filtre par accident.
"""

from contextlib import contextmanager
from contextvars import ContextVar

current_company: ContextVar = ContextVar("current_company", default=None)


class NoCurrentCompanyError(RuntimeError):
    """Requête métier sans entreprise courante : erreur de programmation."""


def get_current_company(required: bool = True):
    company = current_company.get()
    if company is None and required:
        raise NoCurrentCompanyError(
            "Aucune entreprise courante : utilisez tenant_context(company) "
            "ou le gestionnaire all_companies (commandes de plateforme uniquement)."
        )
    return company


@contextmanager
def tenant_context(company):
    """Ouvre le contexte d'une entreprise, puis restaure le précédent."""
    token = current_company.set(company)
    try:
        yield company
    finally:
        current_company.reset(token)
