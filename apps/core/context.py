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
