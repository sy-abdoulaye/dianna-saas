"""Réponses HTMX communes (docs/02-architecture.md, section HTMX).

- Succès d'un formulaire : en-tête HX-Trigger {"toast": {...}, "closeModal": true}.
- Erreur de validation : statut 422, le fragment du formulaire est inséré (ui.js configure
  htmx.config.responseHandling pour accepter les 422).
"""

import json
from dataclasses import asdict, dataclass

from django.http import HttpResponse

TOAST_KINDS = ("ok", "info", "warn", "err")


@dataclass(frozen=True)
class Toast:
    """Notification visuelle. `emphasis` : partie du message mise en gras (nom de la personne).
    `undo_url` : URL d'annulation signée (apps.core.undo), `action` : lien principal."""

    title: str
    message: str = ""
    kind: str = "ok"
    emphasis: str = ""
    action_label: str = ""
    action_url: str = ""
    undo_url: str = ""

    def __post_init__(self):
        if self.kind not in TOAST_KINDS:
            raise ValueError(f"Type de notification inconnu : {self.kind}")

    def as_event(self) -> dict:
        return {key: str(value) for key, value in asdict(self).items() if value}


def trigger(response: HttpResponse, *, toast: Toast | None = None, close_modal=False, **events):
    """Ajoute (ou complète) l'en-tête HX-Trigger de la réponse."""
    payload = json.loads(response.headers.get("HX-Trigger", "{}") or "{}")
    if toast is not None:
        payload["toast"] = toast.as_event()
    if close_modal:
        payload["closeModal"] = True
    payload.update(events)
    # JSON en ASCII (échappements \uXXXX, décodés par htmx) : un caractère hors Latin-1
    # (« € », « Œ ») serait sinon encodé par Django selon la RFC 2047, illisible pour htmx.
    response.headers["HX-Trigger"] = json.dumps(payload)
    return response


def location(response: HttpResponse, path: str) -> HttpResponse:
    """Affiche `path` sans recharger le document (en-tête HX-Location, zone #content) : la
    notification visuelle de la réponse, et son « Annuler », restent à l'écran."""
    if not path.startswith("/") or path.startswith("//"):
        raise ValueError("HX-Location : chemin interne seulement.")
    response.headers["HX-Location"] = json.dumps(
        {"path": path, "target": "#content", "select": "#content", "swap": "outerHTML"}
    )
    return response


# Événement qui recharge toute la zone #content de la page affichée (layouts/app.html).
PAGE_CHANGED = "pageChanged"
# Rechargement du document entier, quand le menu change aussi (after_action).
RELOAD_PAGE = "reloadPage"
MESSAGE_LEVELS = {"ok": "success", "info": "info", "warn": "warning", "err": "error"}


def after_action(
    request,
    toast: Toast,
    *,
    refresh: str | tuple[str, ...] = (),
    go_to: str = "",
    close_modal: bool = False,
    page_form: bool = False,
) -> HttpResponse:
    """Seule fin d'une action réussie (R1-02) : notification visuelle, puis
    - le résultat est sur la même page : la zone concernée se recharge (événement `refresh`,
      `PAGE_CHANGED` pour toute la page) ;
    - le résultat est une autre page : HX-Location vers `go_to` (seule #content change, la
      notification et son « Annuler » restent à l'écran).
    - `refresh=RELOAD_PAGE` : seule exception, quand le cadre de la page change aussi (menu,
      après l'activation d'un module) : le document entier se recharge (HX-Refresh).
    `page_form` : formulaire de page complète, utilisable sans JavaScript ; envoyé sans HTMX,
    il reçoit un message puis une redirection (les modales, elles, demandent HTMX)."""
    if refresh and go_to:
        raise ValueError("after_action : soit refresh, soit go_to.")
    if page_form and not is_htmx(request):
        return _classic_redirect(request, toast, go_to)
    response = toast_response(toast, close_modal=close_modal)
    if refresh == RELOAD_PAGE:
        response["HX-Refresh"] = "true"
        return response
    if go_to:
        return location(response, go_to)
    events = (refresh,) if isinstance(refresh, str) else refresh
    return trigger(response, **dict.fromkeys(events, True))


def _classic_redirect(request, toast: Toast, go_to: str) -> HttpResponse:
    from django.contrib import messages
    from django.shortcuts import redirect
    from django.utils.http import url_has_allowed_host_and_scheme

    getattr(messages, MESSAGE_LEVELS[toast.kind])(request, str(toast.title))
    target = go_to or request.headers.get("referer", "")
    if not url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}):
        target = request.path
    return redirect(target)


def download_response(path: str) -> HttpResponse:
    """Fin d'un export demandé depuis une modale : la modale se ferme et le navigateur
    télécharge le fichier (HX-Redirect vers l'adresse du fichier, qui refait tous les
    contrôles : permission, périmètre, limite de fréquence, journal)."""
    if not path.startswith("/") or path.startswith("//"):
        raise ValueError("HX-Redirect : chemin interne seulement.")
    response = trigger(HttpResponse(status=204), close_modal=True)
    response["HX-Redirect"] = path
    return response


def toast_response(toast: Toast, *, close_modal=False, status=204) -> HttpResponse:
    """Réponse vide qui affiche une notification (et ferme la modale si demandé)."""
    return trigger(HttpResponse(status=status), toast=toast, close_modal=close_modal)


def error_response(
    error,
    *,
    close_modal: bool = False,
    status: int = 409,
    refresh: str | tuple[str, ...] = (),
    go_to: str = "",
    request=None,
) -> HttpResponse:
    """Refus d'un service (ServiceError ou équivalent) : notification visuelle d'erreur. Si
    l'affichage est devenu faux (autre décision prise entre-temps), `refresh` recharge la
    zone concernée ; `go_to` ramène à une autre page (HX-Location, ou message puis
    redirection pour un formulaire de page complète envoyé sans HTMX : passer `request`)."""
    if refresh and go_to:
        raise ValueError("error_response : soit refresh, soit go_to.")
    toast = Toast(title=str(error.message), kind="err")
    if go_to and request is not None and not is_htmx(request):
        return _classic_redirect(request, toast, go_to)
    response = toast_response(toast, close_modal=close_modal, status=status)
    if go_to:
        return location(response, go_to)
    events = (refresh,) if isinstance(refresh, str) else refresh
    return trigger(response, **dict.fromkeys(events, True))


def confirm_response(request, *, title, text, ok_label, action_url, **options):
    """Modale de confirmation commune (components/confirm.html) avant une action. Options :
    `danger` (action destructive), `ok_icon`."""
    from django.shortcuts import render

    context = {
        "title": title,
        "text": text,
        "ok_label": ok_label,
        "danger": options.get("danger", False),
        "action_url": action_url,
        "ok_icon": options.get("ok_icon", ""),
    }
    return render(request, "components/confirm.html", context)


def modal_form_response(request, template: str, context: dict) -> HttpResponse:
    """Modale de formulaire : la modale entière à l'ouverture (GET), le seul fragment `form`
    avec le statut 422 quand l'envoi est refusé (POST)."""
    from django.shortcuts import render

    if request.method == "GET":
        return render(request, template, context)
    return form_error_response(request, template, context)


def form_error_response(request, template: str, context: dict) -> HttpResponse:
    """Formulaire refusé : le seul fragment `form` du gabarit, statut 422 (inséré par HTMX à
    la place du formulaire, focus sur le premier champ à corriger)."""
    from django.shortcuts import render

    return render(request, f"{template}#form", context, status=422)


def is_htmx(request) -> bool:
    return bool(getattr(request, "htmx", False))
