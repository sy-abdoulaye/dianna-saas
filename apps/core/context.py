"""Contexte d'une action : qui agit, et depuis quelle requête (adresse IP du journal).

Passé une seule fois aux fonctions internes des services, au lieu de la paire `actor`,
`request` répétée à chaque appel."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from django.http import HttpRequest

    from apps.people.models import Employee


@dataclass(frozen=True)
class ActionContext:
    actor: "Employee | None"
    request: "HttpRequest | None" = None

    @classmethod
    def of(cls, request: "HttpRequest") -> "ActionContext":
        """Action d'une vue : la personne connectée et sa requête."""
        return cls(getattr(request, "employee", None), request)

    def person(self) -> "Employee":
        """La personne qui agit, pour une action qui en exige une (refus sinon)."""
        if self.actor is None:
            raise ValueError("Cette action exige une personne.")
        return self.actor


# Action sans personne (tâche quotidienne, plateforme) : journal sans auteur.
SYSTEM = ActionContext(None)
