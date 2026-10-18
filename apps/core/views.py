"""Pages d'erreur du design system, notifications et vitrine."""

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_not_required
from django.core.cache import cache
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.csp import CSP
from django.utils.translation import gettext as _
from django.views.decorators.csrf import requires_csrf_token
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from apps.core import notifications
from apps.core.forms import SpaceAccessForm
from apps.core.hosts import company_url
from apps.core.models import Notification
from apps.people.models import Role

ROLE_LABELS = dict(Role.choices)


@requires_csrf_token
def permission_denied(request, exception=None):
    employee = getattr(request, "employee", None)
    context = {"role_label": ROLE_LABELS.get(employee.role) if employee else ""}
    return render(request, "pages/403.html", context, status=403)


@requires_csrf_token
def page_not_found(request, exception=None):
    return render(request, "pages/404.html", status=404)


@requires_csrf_token
def server_error(request):
    # Pas de contexte de mise en page : la base peut être indisponible.
    return render(request, "pages/500.html", {"base_template": "layouts/auth.html"}, status=500)


def module_disabled(request, module_label: str = ""):
    employee = getattr(request, "employee", None)
    context = {
        "module_label": module_label,
        "is_admin": bool(employee and employee.role == Role.ADMIN),
        "admin_url": "",
    }
    return render(request, "pages/module_disabled.html", context, status=403)


# ---------- Notifications ----------


@require_GET
def notification_list(request):
    page = Paginator(notifications.for_employee(request.employee), 20).get_page(
        request.GET.get("page")
    )
    return render(request, "core/notifications.html", {"page_obj": page})


@require_GET
def notification_open(request, pk):
    """Un clic marque la notification comme lue et ouvre l'objet (fiche socle)."""
    notification = get_object_or_404(Notification, pk=pk, recipient=request.employee)
    notifications.mark_read(notification)
    return redirect(notifications.safe_target(notification))


@require_POST
def notification_read_all(request):
    notifications.mark_all_read(request.employee)
    if request.htmx:
        return render(request, "core/partials/bell.html")
    messages.success(request, _("Toutes les notifications sont lues."))
    return redirect("core:notifications")


# ---------- Vitrine (dianna.fr) ----------

ACCESS_RATE = 10  # tentatives par adresse IP et par période
ACCESS_PERIOD = 10 * 60


def _too_many_attempts(request) -> bool:
    key = f"space-access:{request.META.get('REMOTE_ADDR', '')}"
    attempts = cache.get_or_set(key, 0, ACCESS_PERIOD)
    if attempts >= ACCESS_RATE:
        return True
    try:
        cache.incr(key)
    except ValueError:
        cache.set(key, 1, ACCESS_PERIOD)
    return False


def _space_access_csp(request):
    """La vitrine redirige le formulaire vers le sous-domaine de l'entreprise : form-action
    l'autorise pour cette seule page (la CSP s'applique aussi aux redirections)."""
    default = "443" if request.scheme == "https" else "80"
    port = "" if request.get_port() == default else f":{request.get_port()}"
    return {
        **settings.SECURE_CSP,
        "form-action": [CSP.SELF, f"{request.scheme}://*.{settings.BASE_DOMAIN}{port}"],
    }


@login_not_required
@require_http_methods(["GET", "POST"])
def public_home(request):
    response = _public_home(request)
    response._csp_config = _space_access_csp(request)  # même attribut que csp_override
    return response


def _public_home(request):
    """Page vitrine minimale : « Accéder à mon espace » (T-08)."""
    form = SpaceAccessForm(request.POST or None)
    if request.method == "POST":
        if _too_many_attempts(request):
            form.add_error(None, _("Trop de tentatives. Réessayez dans quelques minutes."))
        elif form.is_valid():
            return redirect(company_url(form.company, "/connexion/", request))
    status = 422 if form.errors else 200
    return render(request, "public/home.html", {"form": form}, status=status)
