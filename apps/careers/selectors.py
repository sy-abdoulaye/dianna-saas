"""Lectures de la carrière : qui agit sur un entretien, ce qui attend chacun, les notes de suivi
visibles et les échéances suggérées de l'entretien de parcours (M-08).

Côté manager d'un entretien (évaluation, planification, compte rendu, signature) :
- le manager copié au lancement, s'il est toujours en poste et toujours le manager de la
  personne ;
- sinon les RH et administrateurs, qui tiennent ce rôle sans bandeau ;
- les RH et administrateurs peuvent aussi agir à la place d'un manager présent (M-12) :
  bandeau « Vous agissez à la place de {manager} » et trace au journal.
Personne n'agit côté manager sur son propre entretien.
"""

from datetime import date

from django.db.models import Q, QuerySet
from django.utils import timezone

from apps.approvals import workflow
from apps.careers.models import (
    Competency,
    FollowUpNote,
    Review,
    ReviewCampaign,
    ReviewKind,
    ReviewReason,
    ReviewStep,
    ReviewTraining,
)
from apps.core import permissions
from apps.people.models import IN_POST_STATUSES, Employee

MANAGER_STEPS = (ReviewStep.MANAGER, ReviewStep.MEETING)


def acting_manager(review: Review) -> Employee | None:
    """Manager qui tient son rôle sur l'entretien, ou None (les RH le tiennent alors)."""
    manager = review.manager
    if manager is None or manager.status not in IN_POST_STATUSES:
        return None
    if review.employee.manager_id != manager.pk:
        return None
    return manager


def can_act_as_manager(actor: Employee | None, review: Review) -> bool:
    if actor is None or actor.pk == review.employee_id:
        return False
    manager = acting_manager(review)
    if manager is not None and manager.pk == actor.pk:
        return True
    return workflow.is_hr_or_admin(actor) and permissions.can(actor, "careers.evaluate", review)


def replaced_manager(actor: Employee, review: Review) -> Employee | None:
    """Manager présent remplacé par un RH ou un administrateur (bandeau et journal, M-12)."""
    manager = acting_manager(review)
    if manager is None or manager.pk == actor.pk or not can_act_as_manager(actor, review):
        return None
    return manager


def manager_side(review: Review) -> list[Employee]:
    """Personnes attendues côté manager : le manager, sinon les RH et administrateurs autres
    que la personne (destinataires des notifications et de « Relancer »)."""
    manager = acting_manager(review)
    if manager is not None:
        return [manager]
    return workflow.hr_validators(exclude=review.employee)


def expected_actors(review: Review) -> list[Employee]:
    """Qui doit agir maintenant (notifications, « Relancer », « En attente de … »)."""
    if review.step == ReviewStep.SELF:
        return [review.employee]
    if review.step in MANAGER_STEPS:
        return manager_side(review)
    if review.step == ReviewStep.SIGNATURE:
        waiting = [] if review.employee_signed_at else [review.employee]
        return waiting + ([] if review.manager_signed_at else manager_side(review))
    return []


def _expected_on_manager_side(actor: Employee, review: Review) -> bool:
    manager = acting_manager(review)
    if manager is not None:
        return manager.pk == actor.pk
    return workflow.is_hr_or_admin(actor) and actor.pk != review.employee_id


def is_todo(actor: Employee, review: Review) -> bool:
    """« À faire par vous » : l'étape attend cette personne. Un RH qui peut agir à la place
    d'un manager présent ne voit pas l'entretien dans ses tâches (M-12)."""
    if review.step == ReviewStep.SELF:
        return review.employee_id == actor.pk
    if review.step in MANAGER_STEPS:
        return _expected_on_manager_side(actor, review)
    if review.step == ReviewStep.SIGNATURE:
        if review.employee_id == actor.pk:
            return review.employee_signed_at is None
        return review.manager_signed_at is None and _expected_on_manager_side(actor, review)
    return False


def visible_reviews(viewer: Employee) -> QuerySet[Review]:
    reviews = Review.objects.select_related(
        "employee", "employee__manager", "employee__service", "employee__site", "manager"
    )
    return permissions.scope_queryset(viewer, reviews, "careers.view")


def todo_reviews(viewer: Employee) -> list[Review]:
    open_reviews = visible_reviews(viewer).exclude(step=ReviewStep.CLOSED)
    return [review for review in open_reviews if is_todo(viewer, review)]


def filter_reviews(
    viewer: Employee, reviews: QuerySet[Review], *, q: str, kind: str, progress: str
) -> list[Review]:
    if q:
        reviews = reviews.filter(
            Q(employee__first_name__icontains=q) | Q(employee__last_name__icontains=q)
        )
    if kind in ReviewKind.values:
        reviews = reviews.filter(kind=kind)
    if progress == "en-cours":
        reviews = reviews.exclude(step=ReviewStep.CLOSED)
    elif progress == "clos":
        reviews = reviews.filter(step=ReviewStep.CLOSED)
    rows = list(reviews)
    if progress == "a-faire":
        rows = [review for review in rows if is_todo(viewer, review)]
    return rows


def current_campaign(today: date | None = None) -> ReviewCampaign | None:
    today = today or timezone.localdate()
    return (
        ReviewCampaign.objects.filter(start__lte=today, end__gte=today).order_by("-start").first()
    )


def campaign_progress(viewer: Employee, campaign: ReviewCampaign) -> int:
    """Part des entretiens visibles de la campagne déjà clos (en %)."""
    reviews = visible_reviews(viewer).filter(campaign=campaign)
    total = reviews.count()
    if not total:
        return 0
    return round(reviews.filter(step=ReviewStep.CLOSED).count() * 100 / total)


def planned_meetings(viewer: Employee, today: date | None = None) -> int:
    today = today or timezone.localdate()
    return (
        visible_reviews(viewer)
        .exclude(step=ReviewStep.CLOSED)
        .filter(meeting_date__gte=today)
        .count()
    )


def active_competencies() -> list[Competency]:
    return list(Competency.objects.filter(active=True))


def launch_candidates(viewer: Employee) -> QuerySet[Employee]:
    """Personnes pour qui cette personne peut lancer un entretien (son périmètre)."""
    people = Employee.objects.filter(status__in=IN_POST_STATUSES).order_by(
        "last_name", "first_name"
    )
    return permissions.scope_queryset(viewer, people, "careers.launch")


# ---------- Fiches de suivi ----------


def visible_notes(viewer: Employee, employee: Employee) -> QuerySet[FollowUpNote]:
    """Seule règle de lecture des notes de suivi (page, compteurs, PDF) : les notes publiques
    de la fiche, et les notes privées dont la personne qui regarde est l'auteur. Une note
    privée n'est visible ni par la personne suivie, ni par les RH (docs/04-permissions.md)."""
    if not can_view_file(viewer, employee):
        return FollowUpNote.objects.none()
    return (
        FollowUpNote.objects.filter(employee=employee)
        .filter(Q(is_private=False) | Q(author=viewer))
        .select_related("author")
    )


def public_notes(employee: Employee) -> QuerySet[FollowUpNote]:
    """Notes de l'export PDF : jamais de note privée, même celles de l'auteur (Q4)."""
    return FollowUpNote.objects.filter(employee=employee, is_private=False).select_related("author")


def can_view_file(viewer: Employee, employee: Employee) -> bool:
    """Fiche de suivi : même périmètre que les entretiens (soi, équipe, RH, administrateur)."""
    return permissions.can(viewer, "careers.view", employee)


def follow_up_people(viewer: Employee, q: str = "") -> QuerySet[Employee]:
    """Onglet « Fiches de suivi » : les personnes en poste du périmètre, sauf soi."""
    people = Employee.objects.filter(status__in=IN_POST_STATUSES).exclude(pk=viewer.pk)
    people = permissions.scope_queryset(viewer, people, "careers.view")
    if q:
        people = people.filter(Q(first_name__icontains=q) | Q(last_name__icontains=q))
    return people.select_related("service").order_by("last_name", "first_name")


def last_individual_review(employee: Employee) -> Review | None:
    return (
        Review.objects.filter(employee=employee, kind=ReviewKind.INDIVIDUAL, step=ReviewStep.CLOSED)
        .order_by("-closed_at")
        .first()
    )


def trainings_of(employee: Employee) -> list[str]:
    """Formations retenues lors des entretiens de parcours clos."""
    return list(
        ReviewTraining.objects.filter(
            review__employee=employee, review__step=ReviewStep.CLOSED
        ).values_list("label", flat=True)
    )


# ---------- Échéances de l'entretien de parcours (M-08, à confirmer par un juriste) ----------


def add_years(day: date, years: int) -> date:
    try:
        return day.replace(year=day.year + years)
    except ValueError:  # 29 février
        return day.replace(year=day.year + years, day=28)


def _held_day(review: Review) -> date | None:
    return review.meeting_date or (timezone.localdate(review.held_at) if review.held_at else None)


def _due_after(review: Review | None, years: int) -> date | None:
    held = _held_day(review) if review is not None else None
    return add_years(held, years) if held else None


def suggested_dues(employee: Employee) -> tuple[date | None, date | None]:
    """(prochain entretien de parcours, prochain état des lieux), suggérés et modifiables :
    - premier entretien dans la première année de présence, puis la périodicité de
      l'entreprise (4 ans au plus) après le dernier entretien de parcours réalisé ;
    - état des lieux 8 ans (réglage) après l'arrivée, puis après le dernier état des lieux.
    Une échéance saisie sur le dernier entretien clos l'emporte."""
    company = employee.company
    closed = Review.objects.filter(
        employee=employee, kind=ReviewKind.PROFESSIONAL, step=ReviewStep.CLOSED
    ).order_by("-closed_at")
    last = closed.first()
    last_summary = closed.filter(reason=ReviewReason.SUMMARY).first()
    arrival = employee.arrival_date
    review_due = (last.next_review_due if last else None) or (
        _due_after(last, company.career_review_interval_years)
        if last
        else (add_years(arrival, 1) if arrival else None)
    )
    summary_due = (last.next_summary_due if last else None) or (
        _due_after(last_summary, company.career_summary_interval_years)
        if last_summary
        else (add_years(arrival, company.career_summary_interval_years) if arrival else None)
    )
    return review_due, summary_due
