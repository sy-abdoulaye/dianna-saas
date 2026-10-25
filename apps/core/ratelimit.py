"""Limites de fréquence, comptées en base (L4-17, L1-16).

Toute limite de fréquence passe par ce module, jamais par le cache : un cache local ou borné
peut perdre un compteur quand d'autres clés arrivent, et il n'est pas partagé entre processus.

Fenêtres fixes : une ligne `RateLimitCounter` par (empreinte de la clé, début de fenêtre),
incrémentée en une seule requête PostgreSQL atomique
(INSERT … ON CONFLICT … DO UPDATE SET count = count + 1 RETURNING count). Deux requêtes
simultanées ne peuvent pas lire le même nombre. Les clés sont des empreintes HMAC : ni adresse
IP ni adresse e-mail en clair en base. Les fenêtres expirées sont supprimées par la purge
planifiée (`manage.py purge_task_results`).

Exports : EXPORT_LIMIT exports par personne et par tranche de EXPORT_PERIOD secondes, tous
formats et tous écrans confondus (planning, exports RH, synthèse de campagne)."""

import hashlib
import hmac
from datetime import timedelta

from django.conf import settings
from django.db import connection
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

EXPORT_LIMIT = 10
EXPORT_PERIOD = 10 * 60  # secondes
EXPORT_LIMIT_MESSAGE = _(
    "Vous avez fait 10 exports en moins de 10 minutes. Réessayez dans quelques minutes."
)
# Fenêtres conservées après leur fin, avant purge (la plus longue période utilisée : 24 h,
# relance d'un entretien).
RETENTION = timedelta(days=1)

INCREMENT_SQL = """
    INSERT INTO core_ratelimitcounter (key, window_start, count)
    VALUES (%s, %s, 1)
    ON CONFLICT (key, window_start) DO UPDATE SET count = core_ratelimitcounter.count + 1
    RETURNING count
"""


def digest(key: str) -> str:
    return hmac.new(settings.SECRET_KEY.encode(), key.encode(), hashlib.sha256).hexdigest()


def window_start(period: int, now=None):
    now = now or timezone.now()
    seconds = int(now.timestamp()) // period * period
    return now.fromtimestamp(seconds, tz=now.tzinfo)


def hit(key: str, period: int) -> int:
    """Compte une tentative et renvoie le nombre de la fenêtre courante (atomique)."""
    with connection.cursor() as cursor:
        cursor.execute(INCREMENT_SQL, [digest(key), window_start(period)])
        return cursor.fetchone()[0]


def current(key: str, period: int) -> int:
    from apps.core.models import RateLimitCounter

    row = RateLimitCounter.objects.filter(
        key=digest(key), window_start=window_start(period)
    ).first()
    return row.count if row else 0


def over_limit(key: str, limit: int, period: int) -> bool:
    """Compte une tentative ; vrai si la limite est dépassée."""
    return hit(key, period) > limit


def purge_expired(now=None) -> int:
    from apps.core.models import RateLimitCounter

    limit = (now or timezone.now()) - RETENTION
    return RateLimitCounter.objects.filter(window_start__lt=limit).delete()[0]


def _export_key(employee) -> str:
    return f"exports:{employee.company_id}:{employee.pk}"


def export_allowed(employee) -> bool:
    """Sans compter : reste-t-il un export possible ? (aperçu, validation d'une modale)."""
    return current(_export_key(employee), EXPORT_PERIOD) < EXPORT_LIMIT


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
