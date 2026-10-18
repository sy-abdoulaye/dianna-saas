"""Correspondance centralisée statut → couleur et libellé des badges (docs/05-design-system.md).

Les couleurs sont des rôles du design system : ok (succès), wait (attente), ko (erreur),
info (information), off (neutre). Les libellés reprennent le prototype mot pour mot ; ils
s'accordent avec le nom de l'objet (une demande « Validée », un compte rendu « Validé »).
"""

from dataclasses import dataclass

from django.utils.translation import gettext_lazy as _

KINDS = ("ok", "wait", "ko", "info", "off")


@dataclass(frozen=True)
class Status:
    kind: str
    label: str


STATUSES: dict[str, dict[str, Status]] = {
    # Demandes : télétravail, congés, astreintes, transport, matériel
    "request": {
        "pending": Status("wait", _("En attente")),
        "manager_approved": Status("info", _("Validée par le manager")),
        "approved": Status("ok", _("Validée")),
        "refused": Status("ko", _("Refusée")),
        "cancelled": Status("off", _("Annulée")),
    },
    "employee": {
        "active": Status("ok", _("Actif")),
        "upcoming": Status("info", _("Arrivée prochaine")),
        "left": Status("ko", _("Parti")),
    },
    "survey": {
        "draft": Status("info", _("Brouillon")),
        "open": Status("ok", _("Ouvert")),
        "closed": Status("off", _("Clos")),
    },
    "campaign": {
        "draft": Status("info", _("Brouillon")),
        "open": Status("ok", _("Ouverte")),
        "closed": Status("off", _("Close")),
    },
    "equipment": {
        "in_stock": Status("ok", _("En stock")),
        "assigned": Status("info", _("Attribué")),
        "repair": Status("wait", _("En réparation")),
        "retired": Status("off", _("Retiré")),
    },
    "equipment_issue": {
        "open": Status("wait", _("Ouvert")),
        "closed": Status("off", _("Clos")),
    },
    "report": {
        "draft": Status("info", _("Brouillon")),
        "submitted": Status("wait", _("Envoyé")),
        "approved": Status("ok", _("Validé")),
        "changes_requested": Status("ko", _("Complément demandé")),
    },
    "review": {
        "todo_by_me": Status("wait", _("À faire par vous")),
        "signed": Status("ok", _("Signé")),
        "closed": Status("ok", _("Clos")),
        "overdue": Status("ko", _("Délai dépassé")),
    },
}


def get_status(domain: str, value: str) -> Status:
    """Renvoie le statut d'affichage. Une valeur inconnue est une erreur de programmation."""
    try:
        return STATUSES[domain][value]
    except KeyError as exc:
        raise KeyError(f"Statut inconnu : {domain}.{value}") from exc
