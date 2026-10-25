from urllib.parse import urlsplit

from django.utils.functional import SimpleLazyObject

from apps.core import notifications
from apps.core.access import enabled_modules
from apps.core.files import signed_url
from apps.core.navigation import build_nav


def app(request):
    """Contexte de la mise en page : menu, cloche, gabarit de base des pages d'erreur."""
    employee = getattr(request, "employee", None)
    if employee is None:
        return {"base_template": "layouts/auth.html", "current_employee": None}
    match = getattr(request, "resolver_match", None)
    return {
        "base_template": "layouts/app.html",
        "page_url": page_url(request),
        "current_employee": employee,
        "current_company": request.company,
        "nav_groups": SimpleLazyObject(
            lambda: build_nav(employee, enabled_modules(request), match, _menu_counts(request))
        ),
        # Calculé tout de suite : le pluriel de {% blocktranslate count %} exige un entier.
        "unread_count": notifications.unread_count(employee),
        "latest_notifications": SimpleLazyObject(lambda: notifications.latest(employee)),
        "current_photo_url": SimpleLazyObject(
            lambda: signed_url(employee.photo) if employee.photo else ""
        ),
    }


def page_url(request) -> str:
    """Adresse de la page affichée, que #content recharge après une action (R1-02). Une page
    rendue par un POST (formulaire refusé, 422) garde l'adresse du navigateur (en-tête
    HX-Current-URL), jamais celle du POST."""
    if request.method == "GET":
        return request.get_full_path()
    current = urlsplit(request.headers.get("HX-Current-URL", ""))
    if current.path and current.netloc == request.get_host():
        return current.path + (f"?{current.query}" if current.query else "")
    return request.path


def _menu_counts(request) -> dict:
    from apps.approvals.views import menu_counts
    from apps.interventions.views import menu_count

    return {**menu_counts(request), **menu_count(request)}
