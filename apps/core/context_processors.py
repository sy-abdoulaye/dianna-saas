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
        "current_employee": employee,
        "current_company": request.company,
        "nav_groups": SimpleLazyObject(
            lambda: build_nav(employee, enabled_modules(request), match, _menu_counts(request))
        ),
        "unread_count": SimpleLazyObject(lambda: notifications.unread_count(employee)),
        "latest_notifications": SimpleLazyObject(lambda: notifications.latest(employee)),
        "current_photo_url": SimpleLazyObject(
            lambda: signed_url(employee.photo) if employee.photo else ""
        ),
    }


def _menu_counts(request) -> dict:
    from apps.approvals.views import menu_counts

    return menu_counts(request)
