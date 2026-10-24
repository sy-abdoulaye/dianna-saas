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


def toast_response(toast: Toast, *, close_modal=False, status=204) -> HttpResponse:
    """Réponse vide qui affiche une notification (et ferme la modale si demandé)."""
    return trigger(HttpResponse(status=status), toast=toast, close_modal=close_modal)


def error_response(error, *, close_modal=False, status=409) -> HttpResponse:
    """Refus d'un service (ServiceError ou équivalent) : notification visuelle d'erreur."""
    return toast_response(
        Toast(title=str(error.message), kind="err"), close_modal=close_modal, status=status
    )


def confirm_response(request, *, title, text, ok_label, action_url, danger=False):
    """Modale de confirmation commune (components/confirm.html) avant une action."""
    from django.shortcuts import render

    context = {
        "title": title,
        "text": text,
        "ok_label": ok_label,
        "danger": danger,
        "action_url": action_url,
    }
    return render(request, "components/confirm.html", context)


def modal_form_response(request, template: str, context: dict) -> HttpResponse:
    """Modale de formulaire : la modale entière à l'ouverture (GET), le seul fragment `form`
    avec le statut 422 quand l'envoi est refusé (POST)."""
    from django.shortcuts import render

    if request.method == "GET":
        return render(request, template, context)
    return render(request, f"{template}#form", context, status=422)


def is_htmx(request) -> bool:
    return bool(getattr(request, "htmx", False))
