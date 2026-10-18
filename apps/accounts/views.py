from django.contrib.auth import login
from django.contrib.auth.decorators import login_not_required
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from apps.accounts import services
from apps.accounts.forms import InvitationPasswordForm
from apps.accounts.models import User
from apps.core.middleware import TENANT

BACKEND = "apps.accounts.auth.HostAwareBackend"


def _tenant_only(request):
    if getattr(request, "host_kind", None) != TENANT:
        raise Http404


@login_not_required
@require_http_methods(["GET", "POST"])
def invitation(request, token):
    """Création du mot de passe à la première connexion (fiche socle)."""
    _tenant_only(request)
    found = services.find_invitation(token)
    if found is None:
        raise Http404
    if not found.is_usable:
        return render(request, "accounts/invitation_expired.html", {"token": token}, status=410)
    form = InvitationPasswordForm(request.POST or None, employee=found.employee)
    if request.method == "POST" and form.is_valid():
        try:
            user = services.accept(found, form.cleaned_data["password1"], request=request)
        except services.InvitationError as error:
            form.add_error(None, error.message)
        else:
            login(request, user, backend=BACKEND)
            return redirect("/")
    status = 422 if form.errors else 200
    return render(
        request,
        "accounts/invitation.html",
        {"form": form, "employee": found.employee, "company": request.company},
        status=status,
    )


@login_not_required
@require_POST
def invitation_renew(request, token):
    _tenant_only(request)
    found = services.find_invitation(token)
    if found is None:
        raise Http404
    services.request_renewal(found, request=request)
    return render(request, "accounts/invitation_expired.html", {"token": token, "requested": True})


@require_POST
def theme(request):
    """Enregistre le thème choisi dans le menu utilisateur (User.theme)."""
    value = request.POST.get("theme", "")
    if value not in User.Theme.values:
        return HttpResponse(status=400)
    request.user.theme = value
    request.user.save(update_fields=["theme", "updated_at"])
    return HttpResponse(status=204)
