"""Annulation immédiate depuis une notification visuelle (L0-03).

Le jeton est signé, valable 30 s (settings.UNDO_WINDOW_SECONDS) et lié à l'auteur de
l'action : seul celui qui a agi peut annuler. Le contenu du jeton ne contient aucune donnée
personnelle, seulement le type d'action et l'identifiant public de l'objet.
"""

from collections.abc import Callable
from dataclasses import dataclass

from django.conf import settings
from django.core import signing
from django.utils.translation import gettext_lazy as _

from apps.core.errors import ServiceError

SALT = "dianna.undo"
TOO_LATE_MESSAGE = _("Il est trop tard pour annuler cette action.")


class UndoError(ServiceError):
    """Jeton invalide, expiré ou présenté par une autre personne que l'auteur."""

    def __init__(self, message=TOO_LATE_MESSAGE):
        super().__init__(message)


@dataclass(frozen=True)
class UndoPayload:
    action: str
    target: str


def _actor_key(request) -> str:
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        return f"u{user.pk}"
    if not request.session.session_key:
        request.session.save()
    return f"s{request.session.session_key}"


def make_token(request, action: str, target: str) -> str:
    return signing.dumps({"a": action, "t": str(target), "k": _actor_key(request)}, salt=SALT)


def read_token(request, token: str, max_age: int | None = None) -> UndoPayload:
    window = settings.UNDO_WINDOW_SECONDS if max_age is None else max_age
    try:
        data = signing.loads(token, salt=SALT, max_age=window)
    except signing.SignatureExpired as exc:
        raise UndoError() from exc
    except signing.BadSignature as exc:
        raise UndoError(_("Cette annulation n'est pas valide.")) from exc
    if data.get("k") != _actor_key(request):
        raise UndoError(_("Seul l'auteur de l'action peut l'annuler."))
    return UndoPayload(action=data["a"], target=data["t"])


# ---------- Annulation générique (vue apps.core.views.undo_action) ----------


@dataclass(frozen=True)
class UndoHandler:
    """Traitement d'une action annulée : `run(request, payload)` défait l'action et renvoie la
    notification visuelle (une ServiceError devient un refus, Http404 une page absente) ;
    `refresh` : zone de la page à recharger ensuite."""

    run: Callable
    refresh: str


HANDLERS: dict[str, UndoHandler] = {}


def register(action: str, run: Callable, *, refresh: str) -> None:
    """Inscrit le traitement d'une action annulable (une seule fois par action)."""
    if action in HANDLERS:
        raise ValueError(f"Annulation déjà inscrite : {action}")
    HANDLERS[action] = UndoHandler(run, refresh)
