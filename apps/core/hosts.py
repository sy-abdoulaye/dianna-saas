"""Construction des adresses absolues par hôte (e-mails, redirections de la vitrine)."""

from django.conf import settings


def _origin(host: str, request=None) -> str:
    if request is not None:
        scheme = request.scheme
        port = request.get_port()
        default = "443" if scheme == "https" else "80"
        port = "" if port == default else f":{port}"
    else:
        scheme = settings.SITE_SCHEME
        port = f":{settings.SITE_PORT}" if settings.SITE_PORT else ""
    return f"{scheme}://{host}{port}"


def company_url(company, path: str = "/", request=None) -> str:
    """Adresse dans l'espace de l'entreprise. Avec `request`, reprend son schéma et son port."""
    return _origin(f"{company.slug}.{settings.BASE_DOMAIN}", request) + path


def public_url(path: str = "/", request=None) -> str:
    return _origin(settings.BASE_DOMAIN, request) + path
