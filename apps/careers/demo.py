"""Données de démonstration de la carrière, reprises du prototype (seedEvals, seedSuivi) :
10 entretiens à toutes les étapes, une campagne, des notes de suivi dont une note privée de
Louise Martin. Appelé par `seed_demo` dans le contexte de l'entreprise Exemple SAS."""

from collections.abc import Callable
from datetime import date, timedelta

from django.utils import timezone

from apps.careers.models import (
    Competency,
    FollowUpNote,
    Review,
    ReviewCampaign,
    ReviewObjective,
    ReviewRating,
    ReviewTraining,
)
from apps.careers.services import create_default_competencies
from apps.people.models import Employee

STEPS = {"auto": "self", "manager": "manager", "entretien": "meeting", "signature": "signature"}
KINDS = {"individuel": "individual", "professionnel": "professional"}
NEXT_YEAR_OBJECTIVES = ("06-30", "12-31")

# (personne, type, étape, auto-évaluation, projet, évaluation, notes, objectifs, date de
# l'entretien en jours depuis aujourd'hui, signatures, compte rendu, formations)
REVIEWS = [
    ("p1", "individuel", "manager",
     "J'ai réduit notre délai de première réponse et formé deux nouveaux arrivants. La "
     "certification ITIL est en cours : l'examen est prévu en novembre.",
     "", None, None, (), None, (), "", ()),
    ("p3", "individuel", "entretien",
     "Année chargée mais satisfaisante. J'ai pris la responsabilité de la base de "
     "connaissances.", "",
     ("Thomas est fiable et très apprécié des clients. Il doit déléguer davantage.",
      "Fiabilité, expertise produit.", "Déléguer, prendre la parole en réunion."),
     (4, 3, 3, 4),
     ("Animer un atelier trimestriel de partage", "Devenir référent de la base de connaissances"),
     9, (), "", ()),
    ("p13", "individuel", "auto", "", "", None, None, (), None, (), "", ()),
    ("p24", "individuel", "auto", "", "", None, None, (), None, (), "", ()),
    ("p14", "individuel", "signature",
     "Très bonne première année. Je souhaite évoluer vers le support de niveau 2.", "",
     ("Belle progression, bon esprit d'équipe.", "Esprit d'équipe.",
      "Gagner en autonomie sur les cas complexes."),
     (3, 3, 4, 3), ("Passer au support de niveau 2", "Suivre la formation ITIL 4"),
     -4, ("emp",), "", ()),
    ("p2", "individuel", "clos", "Livraison du module de planning dans les temps.", "",
     ("Excellente année technique.", "Qualité du code.", "Documentation."),
     (3, 4, 3, 4), ("Écrire la documentation technique", "Encadrer un alternant"),
     -12, ("emp", "mgr"), "", ()),
    ("p4", "individuel", "manager",
     "Trois projets livrés, dont la refonte de l'espace client.", "",
     None, None, (), None, (), "", ()),
    ("p1", "professionnel", "clos",
     "Accueil des nouveaux arrivants et formation à la relation client difficile.",
     "Devenir référente support d'ici deux ans.", None, None, (), "2026-03-14",
     ("emp", "mgr"), "Évolution positive. Formation à l'animation accordée, ITIL à valider.",
     ("Animer un atelier (2 jours)", "ITIL 4 Foundation (3 jours)")),
    ("p3", "professionnel", "auto", "", "", None, None, (), None, (), "", ()),
    ("p13", "professionnel", "entretien", "Premier bilan depuis mon arrivée en 2023.",
     "Évoluer vers la formation interne.", None, None, (), 14, (), "", ()),
]  # fmt: skip

# (personne, date du prototype, auteur, type, texte, note privée)
NOTES = [
    ("p1", "2026-10-28", "p5", "review", "Entretien prévu : objectifs 2027 à définir.", False),
    ("p1", "2026-09-12", "p5", "follow_up",
     "Charge élevée en période de congés, renfort demandé sur les astreintes.", False),
    ("p1", "2026-09-12", "p5", "follow_up",
     "À surveiller : risque de surcharge à l'approche de l'examen ITIL.", True),
    ("p1", "2026-06-03", "p1", "wish",
     "Souhait d'évoluer vers un rôle de référente support. Formation à l'animation demandée.",
     False),
    ("p1", "2026-03-14", "p9", "review",
     "Projet de formation validé, deux jours de formation planifiés.", False),
    ("p3", "2026-08-20", "p5", "follow_up",
     "Très bon retour des clients sur la base de connaissances.", False),
]  # fmt: skip


def seed(people: dict[str, Employee], shifted: Callable[[str], date]) -> None:
    create_default_competencies()
    today = timezone.localdate()
    start, end = shifted("2026-10-05"), shifted("2026-12-18")
    campaign = ReviewCampaign.objects.create(label=f"Campagne {start.year}", start=start, end=end)
    competencies = list(Competency.objects.order_by("order"))
    for row in REVIEWS:
        _review(people, row, campaign, competencies, today, shifted)
    for key, day, author, kind, text, private in NOTES:
        FollowUpNote.objects.create(
            employee=people[key],
            author=people[author],
            date=shifted(day),
            kind=kind,
            text=text,
            is_private=private,
        )


def _meeting(value, today: date, shifted) -> date | None:
    if value is None:
        return None
    return today + timedelta(days=value) if isinstance(value, int) else shifted(value)


def _review(people, row, campaign, competencies, today, shifted) -> Review:
    (
        key,
        kind,
        step,
        summary,
        project,
        evaluation,
        scores,
        objectives,
        when,
        signed,
        report,
        trainings,
    ) = row
    employee = people[key]
    meeting = _meeting(when, today, shifted)
    now = timezone.now()
    review = Review.objects.create(
        campaign=campaign,
        employee=employee,
        manager=employee.manager,
        launched_by=employee.manager,
        kind=KINDS[kind],
        reason="periodic" if kind == "professionnel" else "",
        step=STEPS.get(step, "closed"),
        self_summary=summary,
        self_project=project,
        manager_summary=evaluation[0] if evaluation else "",
        strengths=evaluation[1] if evaluation else "",
        improvements=evaluation[2] if evaluation else "",
        report=report,
        meeting_date=meeting,
        held_at=now if step in ("signature", "clos") else None,
        employee_signed_at=now if "emp" in signed else None,
        manager_signed_at=now if "mgr" in signed else None,
        manager_signed_by=employee.manager if "mgr" in signed else None,
        closed_at=now if step == "clos" else None,
    )
    for competency, score in zip(competencies, scores or (), strict=False):
        ReviewRating.objects.create(review=review, competency=competency, score=score)
    for order, (title, suffix) in enumerate(zip(objectives, NEXT_YEAR_OBJECTIVES, strict=False), 1):
        due = date.fromisoformat(f"{today.year + 1}-{suffix}")
        ReviewObjective.objects.create(review=review, order=order, title=title, due_date=due)
    for order, label in enumerate(trainings, 1):
        ReviewTraining.objects.create(review=review, order=order, label=label)
    if step == "clos" and kind == "individuel":
        FollowUpNote.objects.create(
            employee=employee,
            author=employee.manager,
            date=meeting or today,
            kind="review",
            text=f"Entretien individuel {(meeting or today).year} clos et signé.",
            review=review,
        )
    return review
