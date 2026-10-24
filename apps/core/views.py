"""Pages d'erreur du design system, notifications et vitrine."""

from django.contrib.auth.decorators import login_not_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.csrf import requires_csrf_token
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from apps.core import notifications
from apps.core.forms import SpaceAccessForm, email_digest, send_space_link
from apps.core.htmx import Toast, after_action
from apps.core.http import client_ip
from apps.core.models import Notification
from apps.core.ratelimit import over_limit
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


# ---------- Fichiers privés ----------


@login_not_required
@require_GET
def private_file(request, token):
    """Sert un fichier privé d'après une URL signée (5 minutes), seulement sur l'hôte de
    l'entreprise propriétaire du fichier. La signature prouve que la vue qui l'a générée a
    vérifié la permission ; la page de connexion l'utilise pour le logo."""
    from django.core import signing
    from django.http import Http404, HttpResponse

    from apps.core.files import StorageUnavailableError, read_private, read_token

    try:
        data = read_token(token)
    except signing.BadSignature as exc:
        raise Http404 from exc
    company = getattr(request, "company", None)
    if company is None or data.get("c") != str(company.pk):
        raise Http404
    name = data["n"]
    if not name.startswith(f"{company.pk}/") or ".." in name:
        raise Http404
    # Justificatifs : jamais par lien signé (L5-01), seulement par la vue qui vérifie la
    # permission à chaque téléchargement.
    if not name.startswith((f"{company.pk}/photos/", f"{company.pk}/logo/")):
        raise Http404
    # Pas d'exists() : un seul appel au stockage. Fichier absent ou stockage indisponible :
    # 404 rapide ; la page affiche les initiales ou masque le logo (L5-17).
    try:
        data = read_private(name)
    except StorageUnavailableError as exc:
        raise Http404 from exc
    content_type = "image/png" if name.endswith(".png") else "image/jpeg"
    response = HttpResponse(data, content_type=content_type)
    response["Cache-Control"] = "private, max-age=300"
    response["Content-Disposition"] = "inline"
    return response


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
    toast = Toast(title=_("Toutes les notifications sont lues."))
    return after_action(request, toast, go_to=reverse("core:notifications"), page_form=True)


# ---------- Vitrine (dianna.fr) ----------

ACCESS_PERIOD = 10 * 60  # secondes
ACCESS_LIMIT_PER_IP = 10
ACCESS_LIMIT_PER_ADDRESS = 3


def _over_limit(key: str, limit: int) -> bool:
    return over_limit(key, limit, ACCESS_PERIOD)


def _too_many_attempts(request, email: str) -> bool:
    """Limite par adresse IP réelle (proxys de confiance) et par adresse saisie, hachée."""
    by_ip = _over_limit(f"space-access:ip:{client_ip(request)}", ACCESS_LIMIT_PER_IP)
    by_address = _over_limit(f"space-access:email:{email_digest(email)}", ACCESS_LIMIT_PER_ADDRESS)
    return by_ip or by_address


@login_not_required
@require_http_methods(["GET", "POST"])
def public_home(request):
    """Page vitrine « Accéder à mon espace » (T-08, L1-12 variante discrète).

    La réponse est identique que l'adresse corresponde ou non à un compte : le lien vers le
    sous-domaine de l'entreprise est envoyé par e-mail, jamais affiché."""
    form = SpaceAccessForm(request.POST or None)
    sent = False
    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"]
        if _too_many_attempts(request, email):
            form.add_error(None, _("Trop de tentatives. Réessayez dans quelques minutes."))
        else:
            send_space_link(email, request)
            sent = True
    status = 422 if form.errors else 200
    return render(request, "public/home.html", {"form": form, "sent": sent}, status=status)
