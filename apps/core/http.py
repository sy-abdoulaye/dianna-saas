"""Adresse IP réelle du client derrière les proxys de confiance (TRUSTED_PROXY_COUNT).

Avec N proxys de confiance, chacun ajoute l'adresse qu'il voit à la fin de X-Forwarded-For :
l'adresse du client est donc la N-ième en partant de la fin. Les valeurs placées plus à gauche
viennent du client et ne sont jamais crues. Sans proxy (N = 0), REMOTE_ADDR fait foi."""

import ipaddress

from django.conf import settings


def _valid(ip: str | None) -> str | None:
    if not ip:
        return None
    try:
        return str(ipaddress.ip_address(ip.strip()))
    except ValueError:
        return None


def client_ip(request) -> str | None:
    if request is None:
        return None
    count = getattr(settings, "TRUSTED_PROXY_COUNT", 0)
    forwarded = request.headers.get("x-forwarded-for", "")
    if count > 0 and forwarded:
        hops = [hop.strip() for hop in forwarded.split(",") if hop.strip()]
        if len(hops) >= count:
            ip = _valid(hops[-count])
            if ip:
                return ip
    return _valid(request.META.get("REMOTE_ADDR"))


def attachment(content: bytes | str, content_type: str, filename: str):
    """Fichier à télécharger (export) : nom ASCII choisi par l'application, jamais saisi."""
    from django.http import HttpResponse

    response = HttpResponse(content, content_type=content_type)
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
