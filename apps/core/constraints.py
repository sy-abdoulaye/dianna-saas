"""Traduction des erreurs de base (L5-19) : une contrainte violée malgré les contrôles du
service (deux actions simultanées) devient le message de cette contrainte, jamais une erreur
500 ni un message générique faux.

Une seule table, `CONSTRAINT_MESSAGES` : nom de la contrainte → (champ, message). Chaque
application y inscrit ses contraintes au chargement (`register`)."""

from django.utils.functional import Promise
from django.utils.translation import gettext_lazy as _

# Message affiché : texte, ou texte traduit à la demande (gettext_lazy).
Message = str | Promise

CONSTRAINT_MESSAGES: dict[str, tuple[str | None, Message]] = {}

INVALID_VALUE = _("Une valeur saisie est trop longue ou invalide. Vérifiez la saisie.")


def register(messages: dict[str, tuple[str | None, Message]]) -> None:
    """Inscrit les contraintes d'une application ; un nom ne peut être inscrit qu'une fois."""
    taken = set(messages) & set(CONSTRAINT_MESSAGES)
    if taken:
        raise ValueError(f"Contraintes déjà inscrites : {sorted(taken)}")
    CONSTRAINT_MESSAGES.update(messages)


def constraint_name(exc) -> str:
    cause = exc.__cause__ or exc.__context__
    diag = getattr(cause, "diag", None)
    return getattr(diag, "constraint_name", "") or ""


def translate(exc, default: Message) -> tuple[str | None, Message]:
    """(champ, message) de la contrainte en cause, ou (None, `default`) si elle est inconnue."""
    return CONSTRAINT_MESSAGES.get(constraint_name(exc), (None, default))
