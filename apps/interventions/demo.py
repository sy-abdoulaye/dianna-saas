"""Données de démonstration du suivi d'intervention, reprises du prototype
(seedInterventions) : 4 comptes rendus validé, brouillon, envoyé (à valider par Louise
Martin) et complément demandé. Appelé par `seed_demo` dans le contexte d'Exemple SAS."""

from collections.abc import Callable
from datetime import date

from django.utils import timezone

from apps.interventions.models import InterventionReport, Mission, ReportEvent, ReportItem
from apps.people.models import Employee

STATUSES = {
    "valide": "approved",
    "brouillon": "draft",
    "envoye": "submitted",
    "revoir": "changes_requested",
}
VISIBILITY = {
    "Fin prévue": "planned_end",
    "Prolongation probable": "extension_likely",
    "Incertaine": "uncertain",
}

# Travail : (descriptif, difficultés, solutions, %, délai, commentaires) ; prévu : sans
# difficultés ni solutions.
REPORTS = [
    {
        "key": "p1", "mission": "Support niveau 2 · contrat Atlas", "period": "2026-09",
        "status": "valide",
        "done": [
            ("Traitement des tickets de niveau 2 sur la messagerie",
             "Volume élevé en début de mois", "Tri quotidien avec l'équipe niveau 1", 100,
             "2026-09-30", ""),
            ("Rédaction de 6 fiches de la base de connaissances", "", "", 75, "2026-10-15",
             "Deux fiches en relecture"),
        ],
        "next": [
            ("Terminer les fiches de la base de connaissances", 100, "2026-10-15", ""),
            ("Former Pierre Blanc au niveau 2", 50, "2026-10-31", ""),
        ],
        "visibility": "Prolongation probable", "end": "2026-12-31", "until": "2027-06-30",
        "follow_up": "Le client souhaite prolonger le contrat de six mois.",
        "note": "Très bon suivi, merci.", "events": [("p1", "submitted"), ("p5", "approved")],
    },
    {
        "key": "p1", "mission": "Support niveau 2 · contrat Atlas", "period": "2026-10",
        "status": "brouillon",
        "done": [
            ("Finalisation des fiches de la base de connaissances",
             "Validation client plus lente que prévu", "Relance hebdomadaire du référent client",
             90, "2026-10-15", ""),
        ],
        "next": [("Mise à jour des procédures d'astreinte", 30, "2026-11-20", "")],
        "visibility": "Prolongation probable", "end": "2026-12-31", "until": "2027-06-30",
        "follow_up": "", "note": "", "events": [],
    },
    {
        "key": "p3", "mission": "Migration de la messagerie · Groupe Horizon",
        "period": "2026-10", "status": "envoye",
        "done": [
            ("Migration de 420 boîtes aux lettres", "Quotas dépassés sur 12 boîtes",
             "Archivage préalable avec les utilisateurs concernés", 80, "2026-10-24",
             "Reste le site de Nantes"),
            ("Plan de communication aux utilisateurs", "", "", 100, "2026-10-10", ""),
        ],
        "next": [
            ("Migration du site de Nantes (85 boîtes)", 100, "2026-11-07",
             "Créneau validé avec le client"),
            ("Bilan et clôture du projet", 0, "2026-11-21", ""),
        ],
        "visibility": "Fin prévue", "end": "2026-11-21", "until": "",
        "follow_up": "Prévoir un point de clôture avec le client.", "note": "",
        "events": [("p3", "submitted")],
    },
    {
        "key": "p2", "mission": "Refonte de l'espace client", "period": "2026-10",
        "status": "revoir",
        "done": [
            ("Développement du module de paiement", "Dépendance à l'API bancaire",
             "Bouchon de test en attendant l'accès", 60, "2026-10-31", ""),
        ],
        "next": [("Tests de bout en bout", 0, "2026-11-15", "")],
        "visibility": "Incertaine", "end": "2026-11-30", "until": "", "follow_up": "",
        "note": "Précise le risque de retard lié à l'API bancaire et la date de fin réaliste.",
        "events": [("p2", "submitted"), ("p6", "changes_requested")],
    },
]  # fmt: skip


def seed(people: dict[str, Employee], shifted: Callable[[str], date]) -> None:
    for spec in REPORTS:
        _report(people, spec, shifted)


def _report(people, spec: dict, shifted) -> InterventionReport:
    mission, _created = Mission.objects.get_or_create(name=spec["mission"])
    status = STATUSES[spec["status"]]
    report = InterventionReport.objects.create(
        employee=people[spec["key"]],
        mission=mission,
        period=shifted(f"{spec['period']}-01").replace(day=1),
        status=status,
        visibility=VISIBILITY[spec["visibility"]],
        planned_end=shifted(spec["end"]),
        extension_wanted=bool(spec["until"]),
        extension_until=shifted(spec["until"]) if spec["until"] else None,
        follow_up=spec["follow_up"],
        reviewer_note=spec["note"],
        submitted_at=timezone.now() if status != "draft" else None,
    )
    for order, (text, difficulties, solutions, percent, due, comments) in enumerate(
        spec["done"], 1
    ):
        ReportItem.objects.create(
            report=report,
            section="done",
            order=order,
            description=text,
            difficulties=difficulties,
            solutions=solutions,
            completion=percent,
            due_date=shifted(due),
            comments=comments,
        )
    for order, (text, percent, due, comments) in enumerate(spec["next"], 1):
        ReportItem.objects.create(
            report=report,
            section="next",
            order=order,
            description=text,
            completion=percent,
            due_date=shifted(due),
            comments=comments,
        )
    for actor, action in spec["events"]:
        comment = spec["note"] if action != "submitted" else ""
        ReportEvent.objects.create(
            report=report, actor=people[actor], action=action, comment=comment
        )
    return report
