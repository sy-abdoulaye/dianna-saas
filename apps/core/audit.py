"""Écriture du journal d'audit (AuditLog). Appelé par les services, jamais par les gabarits.

Ne jamais passer de contenu personnel dans `summary` : seulement l'action et, au besoin, le
nom de la personne concernée (déjà visible dans l'application par les administrateurs)."""

from apps.core.http import client_ip
from apps.core.models import AuditLog


def log(action: str, summary: str, *, actor=None, target=None, request=None, company=None):
    entry = AuditLog(
        actor=actor,
        action=action,
        summary=summary[:255],
        target_type=target._meta.label_lower if target is not None else "",
        target_id=str(getattr(target, "public_id", None) or getattr(target, "pk", "") or "")
        if target is not None
        else "",
        ip=client_ip(request),
    )
    if company is not None:
        entry.company = company
    entry.save()
    return entry
