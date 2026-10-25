"""Résolution de l'hôte et de l'entreprise courante (T-07, T-08, T-22).

- `<BASE_DOMAIN>` (et `www.`) : page vitrine, routes config.urls_public ;
- `admin.<BASE_DOMAIN>` : administration éditeur seule, routes config.urls_platform ;
- `<slug>.<BASE_DOMAIN>` : espace de l'entreprise, routes config.urls.
Un sous-domaine inconnu renvoie 404 ; une entreprise suspendue, une page dédiée (503).
L'entreprise est placée dans request.company et dans la ContextVar, remise à zéro dans un
`finally` pour qu'aucune requête n'hérite de l'entreprise d'une autre.
"""

from django.conf import settings
from django.contrib.auth import logout
from django.shortcuts import render
from django.utils.cache import patch_cache_control, patch_vary_headers

from apps.core.models import Company
from apps.core.tenancy import current_company

PUBLIC, PLATFORM, TENANT = "public", "platform", "tenant"


def classify_host(host: str):
    """Renvoie (type d'hôte, slug ou None) pour un nom d'hôte sans port."""
    host = (host or "").lower().rstrip(".")
    base = settings.BASE_DOMAIN
    if host in (base, f"www.{base}"):
        dev_slug = getattr(settings, "DEV_COMPANY_SLUG", "")
        if dev_slug and settings.DEBUG and host == base:
            return TENANT, dev_slug
        return PUBLIC, None
    if host == f"{settings.PLATFORM_SUBDOMAIN}.{base}":
        return PLATFORM, None
    suffix = f".{base}"
    if host.endswith(suffix):
        slug = host[: -len(suffix)]
        if slug and "." not in slug:
            return TENANT, slug
    return None, None


class CompanyMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        kind, slug = classify_host(request.get_host().split(":")[0])
        request.host_kind = kind
        request.company = None
        if kind == PUBLIC:
            request.urlconf = "config.urls_public"
        elif kind == PLATFORM:
            request.urlconf = "config.urls_platform"
        elif kind == TENANT:
            company = Company.objects.filter(slug=slug).first()
            if company is None:
                request.urlconf = "config.urls_public"
                return render(request, "pages/404.html", status=404)
            if not company.is_active:
                return render(request, "pages/suspended.html", {"company": company}, status=503)
            request.company = company
        else:
            return render(request, "pages/404.html", status=404)

        token = current_company.set(request.company)
        try:
            return self.get_response(request)
        finally:
            current_company.reset(token)


class EmployeeMiddleware:
    """Rattache la fiche de l'utilisateur connecté (request.employee).

    Défense en profondeur : une session dont le compte n'appartient pas à l'entreprise de
    l'hôte est fermée. Sur l'hôte éditeur, seule l'équipe Dianna reste connectée. Un membre
    de l'équipe Dianna n'a aucun droit particulier sur un sous-domaine client (T-22)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.employee = None
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            if request.host_kind == TENANT:
                employee = getattr(user, "employee", None)
                if (
                    employee is None
                    or employee.company_id != request.company.pk
                    or not employee.can_sign_in
                ):
                    logout(request)
                else:
                    request.employee = employee
            elif request.host_kind == PLATFORM and not user.is_staff:
                logout(request)
            elif request.host_kind == PUBLIC and not (settings.DEBUG and user.is_staff):
                # La vitrine n'a pas de session ; en développement seulement, /editeur/ y
                # garde la session de l'équipe Dianna (L0-13).
                logout(request)
        return self.get_response(request)


class HtmxCacheMiddleware:
    """Une même adresse rend la page entière ou un fragment selon l'en-tête HX-Request : le
    navigateur doit les distinguer (Vary) et ne jamais garder un fragment (no-store), sinon
    Retour puis Suivant affiche le fragment nu à la place de la page."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        patch_vary_headers(response, ("HX-Request",))
        if request.headers.get("HX-Request") == "true":
            patch_cache_control(response, no_store=True)
        return response
