"""Entreprise courante (T-07, docs/02-architecture.md).

L'entreprise de la requête est posée par CompanyMiddleware dans une ContextVar, remise à
zéro à la fin de chaque requête. Les tâches et les commandes ouvrent le contexte avec
`with tenant_context(company):`. Un queryset de TenantManager est lié à l'entreprise courante
au moment de sa construction ; à l'évaluation, il lève NoCurrentCompanyError sans entreprise
courante et CompanyMismatchError si l'entreprise a changé (ou s'il a été construit sans
entreprise) : aucune requête métier ne peut partir sans le bon filtre par accident.
"""

from contextlib import contextmanager
from contextvars import ContextVar

current_company: ContextVar = ContextVar("current_company", default=None)


class NoCurrentCompanyError(RuntimeError):
    """Requête métier sans entreprise courante : erreur de programmation."""


class CompanyMismatchError(RuntimeError):
    """Queryset évalué dans une autre entreprise que celle de sa construction (ou construit
    sans entreprise courante) : erreur de programmation, par exemple un queryset déclaré au
    niveau d'une classe."""


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
