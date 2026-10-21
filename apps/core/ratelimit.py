"""Limites de fréquence (cache partagé : table `dianna_cache` en production).

Exports (L4-17) : EXPORT_LIMIT exports par personne et par tranche de EXPORT_PERIOD secondes,
tous formats et tous écrans confondus (planning, exports RH, synthèse de campagne)."""

from django.core.cache import cache
from django.utils.translation import gettext_lazy as _

EXPORT_LIMIT = 10
EXPORT_PERIOD = 10 * 60  # secondes
EXPORT_LIMIT_MESSAGE = _(
    "Vous avez fait 10 exports en moins de 10 minutes. Réessayez dans quelques minutes."
)


def over_limit(key: str, limit: int, period: int) -> bool:
    """Compte une tentative ; vrai si la limite est dépassée."""
    cache.add(key, 0, period)
    try:
        attempts = cache.incr(key)
    except ValueError:  # entrée expirée entre add et incr
        cache.set(key, 1, period)
        attempts = 1
    return attempts > limit


def _export_key(employee) -> str:
    return f"exports:{employee.company_id}:{employee.pk}"


def export_allowed(employee) -> bool:
    """Sans compter : reste-t-il un export possible ? (aperçu, validation d'une modale)."""
    return (cache.get(_export_key(employee)) or 0) < EXPORT_LIMIT


def record_export(employee) -> bool:
    """Compte un export ; faux si la limite est dépassée (rien n'est alors généré)."""
    return not over_limit(_export_key(employee), EXPORT_LIMIT, EXPORT_PERIOD)


def export_limited_response(request, back_url: str):
    """Page « Trop d'exports en peu de temps » (statut 429), rien n'est généré."""
    from django.shortcuts import render

    return render(
        request,
        "pages/export_limited.html",
        {"message": EXPORT_LIMIT_MESSAGE, "back_url": back_url},
        status=429,
    )
