"""Pages d'erreur du design system : 403, 404, 500 et « Module désactivé »."""

from django.shortcuts import render
from django.views.decorators.csrf import requires_csrf_token


@requires_csrf_token
def permission_denied(request, exception=None):
    return render(request, "pages/403.html", status=403)


@requires_csrf_token
def page_not_found(request, exception=None):
    return render(request, "pages/404.html", status=404)


@requires_csrf_token
def server_error(request):
    return render(request, "pages/500.html", status=500)


def module_disabled(request, module_label: str = ""):
    """Utilisé par le décorateur module_required (lot 1)."""
    return render(request, "pages/module_disabled.html", {"module_label": module_label}, status=403)
