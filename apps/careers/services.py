"""Services de la carrière (docs/modules/10-carriere.md).

Une fonction par transition d'entretien : chacune verrouille l'entretien, vérifie l'étape de
départ et la personne qui agit, enregistre, notifie la personne suivante et écrit le journal.
Un RH ou un administrateur qui agit à la place d'un manager présent est tracé au journal
(« à la place de … », M-12).
"""

from dataclasses import dataclass, field
from datetime import date

from django.db import IntegrityError, transaction
from django.db.models import Max
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from apps.careers import selectors
from apps.careers.models import (
    Competency,
    FollowUpNote,
    Review,
    ReviewCampaign,
    ReviewKind,
    ReviewObjective,
    ReviewRating,
    ReviewReason,
    ReviewStep,
    ReviewTraining,
)
from apps.core import audit, constraints, notifications, permissions, ratelimit
from apps.core.context import ActionContext
from apps.core.dates import format_date
from apps.core.errors import ServiceError
from apps.core.models import Notification
from apps.people.models import Employee


class CareerError(ServiceError):
    """Refus d'une action de carrière (message affiché, champ éventuel)."""


ALREADY_DONE = gettext_lazy("Cette étape a déjà été complétée.")
NOT_YOUR_TURN = gettext_lazy("Vous ne pouvez pas compléter cette étape.")
ALL_RATINGS = gettext_lazy("Notez toutes les compétences de 1 à 4.")
PAST_DATE = gettext_lazy("La date ne peut pas être dans le passé.")
REMIND_PERIOD = 24 * 60 * 60  # une relance par entretien et par 24 h (Q11)

constraints.register(
    {
        "careers_one_open_review_per_kind": (
            "employee",
            gettext_lazy("Un entretien de ce type est déjà en cours pour cette personne."),
        ),
        "careers_reason_matches_kind": (
            "reason",
            gettext_lazy("Choisissez le motif de l'entretien de parcours."),
        ),
        "careers_competency_name_ci_unique": (
            "name",
            gettext_lazy("Cette compétence existe déjà."),
        ),
        "careers_campaign_end_after_start": (
            "end",
            gettext_lazy("La fin doit être après le début."),
        ),
        "careers_rating_unique": (None, ALL_RATINGS),
        "careers_rating_score_range": (None, ALL_RATINGS),
    }
)

DEFAULT_COMPETENCIES = (
    (gettext_lazy("Relation client"), gettext_lazy("Écoute, clarté des réponses")),
    (gettext_lazy("Autonomie"), gettext_lazy("Initiative, organisation")),
    (gettext_lazy("Travail en équipe"), gettext_lazy("Partage, entraide")),
    (gettext_lazy("Maîtrise des outils"), gettext_lazy("Outils et méthodes du poste")),
)


# ---------- Outils communs ----------


def review_url(review: Review) -> str:
    return reverse("careers:detail", args=[review.public_id])


def _lock(review: Review) -> Review:
    return (
        Review.objects.select_for_update(of=("self",))
        .select_related("employee", "employee__manager", "manager", "employee__company")
        .get(pk=review.pk)
    )


def _expect_step(review: Review, step: str) -> None:
    if review.step != step:
        raise CareerError(ALREADY_DONE)


def _expect_manager_side(actor: Employee, review: Review) -> None:
    if not selectors.can_act_as_manager(actor, review):
        raise CareerError(NOT_YOUR_TURN)


def _advance(review: Review) -> None:
    steps = review.steps
    index = steps.index(review.step)
    review.step = steps[index + 1] if index + 1 < len(steps) else ReviewStep.CLOSED


def _audit(review: Review, action: str, verb: str, context: ActionContext) -> None:
    """Journal de l'entretien, sans contenu saisi ; « à la place de … » si un RH remplace un
    manager présent (M-12)."""
    summary = _("%(verb)s : %(kind)s de %(name)s") % {
        "verb": verb,
        "kind": review.get_kind_display().lower(),
        "name": review.employee.full_name,
    }
    replaced = (
        selectors.replaced_manager(context.actor, review) if context.actor is not None else None
    )
    if replaced is not None:
        summary += " " + _("(à la place de %(name)s)") % {"name": replaced.full_name}
    audit.log(
        f"careers.{action}", summary, actor=context.actor, target=review, request=context.request
    )


def _notify(
    review: Review, recipients: list[Employee], text: str, *, email_subject: str = ""
) -> list[Notification]:
    return notifications.notify_many(
        recipients, text, url=review_url(review), email_subject=email_subject, source=review
    )


def _notify_next(review: Review, text: str, context: ActionContext) -> None:
    """Prévient les personnes attendues à la nouvelle étape, sauf celle qui vient d'agir."""
    actor_pk = context.actor.pk if context.actor is not None else None
    recipients = [p for p in selectors.expected_actors(review) if p.pk != actor_pk]
    if recipients:
        _notify(review, recipients, text)


def _kind_label(review: Review) -> str:
    return str(review.get_kind_display())


# ---------- Lancement ----------


@transaction.atomic
def launch_review(employee: Employee, kind: str, reason: str, *, context: ActionContext) -> Review:
    """Lance un entretien ; refusé si un entretien du même type est déjà en cours (verrou de
    la fiche, puis contrainte de base)."""
    actor = context.person()
    employee = (
        Employee.objects.select_for_update(of=("self",))
        .select_related("manager")
        .get(pk=employee.pk)
    )
    if not permissions.can(actor, "careers.launch", employee):
        raise CareerError(_("Vous ne pouvez pas lancer d'entretien pour cette personne."))
    if Review.objects.filter(employee=employee, kind=kind).exclude(step=ReviewStep.CLOSED).exists():
        raise CareerError(
            _("Un entretien de ce type est déjà en cours pour %(name)s.")
            % {"name": employee.full_name},
            "employee",
        )
    review = Review(
        employee=employee,
        manager=employee.manager,
        launched_by=actor,
        kind=kind,
        reason=reason if kind == ReviewKind.PROFESSIONAL else "",
        campaign=selectors.current_campaign(),
    )
    _save(review)
    task = (
        _("complétez votre auto-évaluation")
        if kind == ReviewKind.INDIVIDUAL
        else _("complétez votre préparation")
    )
    text = f"{_kind_label(review)} : {task}"
    _notify(review, [employee], text, email_subject=_kind_label(review))
    _audit(review, "launched", _("Entretien lancé"), context)
    return review


def _save(review: Review) -> None:
    try:
        with transaction.atomic():
            review.save()
    except IntegrityError as exc:
        field_name, message = constraints.translate(exc, ALREADY_DONE)
        raise CareerError(message, field_name) from exc


@transaction.atomic
def undo_launch(public_id: str, *, context: ActionContext) -> None:
    """« Annuler » après le lancement : l'entretien et sa notification disparaissent, tant
    que le salarié n'a rien saisi."""
    actor = context.person()
    review = (
        Review.objects.select_for_update()
        .select_related("employee")
        .filter(public_id=public_id, launched_by=actor)
        .first()
    )
    if review is None or review.step != ReviewStep.SELF or review.self_summary:
        raise CareerError(_("L'entretien a déjà commencé : il ne peut plus être retiré."))
    Notification.objects.filter(source_type="review", source_id=review.pk).delete()
    _audit(review, "launch_undone", _("Lancement annulé"), context)
    review.delete()


# ---------- Étapes ----------


@transaction.atomic
def submit_self(review: Review, *, summary: str, project: str, context: ActionContext) -> Review:
    """Auto-évaluation (individuel) ou préparation (parcours) : le salarié seulement."""
    actor = context.person()
    review = _lock(review)
    _expect_step(review, ReviewStep.SELF)
    if actor.pk != review.employee_id:
        raise CareerError(NOT_YOUR_TURN)
    review.self_summary, review.self_project = summary, project
    _advance(review)
    review.save()
    what = (
        _("son auto-évaluation")
        if review.kind == ReviewKind.INDIVIDUAL
        else _("son dossier de préparation")
    )
    _notify_next(review, f"{review.employee.full_name} a envoyé {what}", context)
    _audit(review, "self_submitted", review.step_label(ReviewStep.SELF), context)
    return review


@dataclass(frozen=True)
class Evaluation:
    """Évaluation du manager (entretien individuel). `ratings` : {compétence: note de 1 à 4} ;
    `objectives` : [(objectif, échéance)], un au moins."""

    summary: str
    strengths: str
    improvements: str
    ratings: dict[int, int]
    objectives: list[tuple[str, date]] = field(default_factory=list)


@transaction.atomic
def submit_evaluation(review: Review, evaluation: Evaluation, *, context: ActionContext) -> Review:
    actor = context.person()
    review = _lock(review)
    _expect_step(review, ReviewStep.MANAGER)
    if review.kind != ReviewKind.INDIVIDUAL:
        raise CareerError(ALREADY_DONE)
    _expect_manager_side(actor, review)
    competencies = selectors.active_competencies()
    ratings = evaluation.ratings
    if any(not 1 <= ratings.get(c.pk, 0) <= 4 for c in competencies):
        raise CareerError(ALL_RATINGS, "ratings")
    if not evaluation.objectives:
        raise CareerError(_("Indiquez au moins un objectif."), "objectives")
    review.manager_summary = evaluation.summary
    review.strengths, review.improvements = evaluation.strengths, evaluation.improvements
    review.ratings.all().delete()
    for competency in competencies:
        ReviewRating.objects.create(
            review=review, competency=competency, score=ratings[competency.pk]
        )
    review.objectives.all().delete()
    for order, (title, due_date) in enumerate(evaluation.objectives, 1):
        ReviewObjective.objects.create(review=review, order=order, title=title, due_date=due_date)
    _advance(review)
    review.save()
    text = _("Votre manager a rédigé son évaluation : l'entretien peut être planifié")
    _notify_next(review, text, context)
    _audit(review, "evaluated", _("Évaluation enregistrée"), context)
    return review


@transaction.atomic
def plan_meeting(
    review: Review, *, meeting_date: date, place: str, context: ActionContext
) -> Review:
    actor = context.person()
    review = _lock(review)
    _expect_step(review, ReviewStep.MEETING)
    _expect_manager_side(actor, review)
    if meeting_date < timezone.localdate():
        raise CareerError(PAST_DATE, "meeting_date")
    review.meeting_date, review.meeting_place = meeting_date, place
    review.save(update_fields=["meeting_date", "meeting_place", "updated_at"])
    when = format_date(meeting_date, "long")
    text = (
        _("Entretien planifié le %(date)s (%(place)s)") % {"date": when, "place": place}
        if place
        else _("Entretien planifié le %(date)s") % {"date": when}
    )
    _notify(review, [review.employee], text)
    _audit(review, "planned", _("Entretien planifié"), context)
    return review


@transaction.atomic
def mark_held(review: Review, *, context: ActionContext) -> Review:
    """« Marquer l'entretien comme réalisé » : à partir de la date planifiée seulement."""
    actor = context.person()
    review = _lock(review)
    _expect_step(review, ReviewStep.MEETING)
    _expect_manager_side(actor, review)
    if review.meeting_date is None:
        raise CareerError(_("Planifiez une date pour pouvoir clore cette étape."))
    if review.meeting_date > timezone.localdate():
        raise CareerError(
            _("L'entretien pourra être marqué comme réalisé à partir du %(date)s.")
            % {"date": format_date(review.meeting_date, "long")}
        )
    review.held_at = timezone.now()
    _advance(review)
    review.save()
    text = (
        _("Le compte rendu de votre entretien de parcours va être rédigé")
        if review.step == ReviewStep.MANAGER
        else _("Votre entretien est prêt à être signé")
    )
    _notify_next(review, text, context)
    _audit(review, "held", _("Entretien réalisé"), context)
    return review


@dataclass(frozen=True)
class ParcoursReport:
    """Compte rendu de l'entretien de parcours. `summary_criteria` : les 3 critères de l'état
    des lieux (oui, non, None : non renseigné), seulement au motif « état des lieux »."""

    report: str
    trainings: list[str] = field(default_factory=list)
    next_review_due: date | None = None
    next_summary_due: date | None = None
    summary_criteria: tuple[bool | None, bool | None, bool | None] = (None, None, None)


@transaction.atomic
def submit_report(review: Review, data: ParcoursReport, *, context: ActionContext) -> Review:
    actor = context.person()
    review = _lock(review)
    _expect_step(review, ReviewStep.MANAGER)
    if review.kind != ReviewKind.PROFESSIONAL:
        raise CareerError(ALREADY_DONE)
    _expect_manager_side(actor, review)
    review.report = data.report
    review.next_review_due, review.next_summary_due = data.next_review_due, data.next_summary_due
    if review.reason == ReviewReason.SUMMARY:
        (
            review.summary_training,
            review.summary_certification,
            review.summary_progression,
        ) = data.summary_criteria
    review.trainings.all().delete()
    for order, label in enumerate(data.trainings, 1):
        ReviewTraining.objects.create(review=review, order=order, label=label)
    _advance(review)
    review.save()
    text = _("Le compte rendu de votre entretien de parcours est prêt à signer")
    _notify_next(review, text, context)
    _audit(review, "reported", _("Compte rendu enregistré"), context)
    return review


@transaction.atomic
def sign(review: Review, *, comment: str = "", context: ActionContext) -> Review:
    """Signature simple (M-09) : elle confirme la tenue de l'entretien, pas l'accord du
    salarié. Le salarié signe pour lui ; côté manager, le manager ou, à sa place, un RH ou un
    administrateur. Personne ne signe les deux côtés. Les deux signatures closent
    l'entretien et ajoutent une note à la fiche de suivi."""
    actor = context.person()
    review = _lock(review)
    _expect_step(review, ReviewStep.SIGNATURE)
    now = timezone.now()
    if actor.pk == review.employee_id:
        if review.employee_signed_at:
            raise CareerError(_("Vous avez déjà signé cet entretien."))
        review.employee_signed_at, review.employee_comment = now, comment
    else:
        _expect_manager_side(actor, review)
        if review.manager_signed_at:
            raise CareerError(_("Cet entretien est déjà signé côté manager."))
        manager = selectors.acting_manager(review)
        review.manager_signed_at, review.manager_signed_by = now, actor
        review.signed_by_hr = manager is None or manager.pk != actor.pk
    _audit(review, "signed", _("Entretien signé"), context)
    if review.employee_signed_at and review.manager_signed_at:
        _close(review, context)
    review.save()
    return review


def _close(review: Review, context: ActionContext) -> None:
    review.step, review.closed_at = ReviewStep.CLOSED, timezone.now()
    year = timezone.localdate(review.held_at).year if review.held_at else timezone.now().year
    title = f"{_kind_label(review)} {year}"
    FollowUpNote.objects.create(
        employee=review.employee,
        author=review.manager_signed_by or context.person(),
        date=timezone.localdate(),
        kind=FollowUpNote.Kind.REVIEW,
        text=_("%(title)s clos et signé.") % {"title": title},
        review=review,
    )
    _notify(review, [review.employee], _("%(title)s clos") % {"title": title})
    audit.log(
        "careers.closed",
        _("Entretien clos : %(kind)s de %(name)s")
        % {"kind": review.get_kind_display().lower(), "name": review.employee.full_name},
        actor=context.actor,
        target=review,
        request=context.request,
    )


def remind(review: Review, *, context: ActionContext) -> int:
    """« Relancer » (Manager et RH) : une notification aux personnes attendues, au plus une
    fois par entretien et par 24 h (ratelimit). Renvoie le nombre de personnes relancées."""
    actor = context.person()
    if actor.pk == review.employee_id or not permissions.can(actor, "careers.evaluate", review):
        raise CareerError(_("Vous ne pouvez pas relancer cet entretien."))
    recipients = [p for p in selectors.expected_actors(review) if p.pk != actor.pk]
    if review.is_closed or not recipients:
        raise CareerError(_("Personne n'est à relancer pour cet entretien."))
    if ratelimit.over_limit(f"careers.remind:{review.pk}", 1, REMIND_PERIOD):
        raise CareerError(_("Une relance a déjà été envoyée ces dernières 24 heures."))
    text = _("Rappel : %(kind)s de %(name)s en attente") % {
        "kind": review.get_kind_display().lower(),
        "name": review.employee.full_name,
    }
    _notify(review, recipients, text)
    _audit(review, "reminded", _("Relance envoyée"), context)
    return len(recipients)


# ---------- Notes de suivi ----------


@transaction.atomic
def add_note(
    employee: Employee, *, kind: str, text: str, is_private: bool, context: ActionContext
) -> FollowUpNote:
    """Note de suivi. Sur sa propre fiche, un salarié n'écrit qu'un « Souhait », jamais privé
    (décision du lot 7) ; une note privée n'est visible que par son auteur."""
    actor = context.person()
    if not permissions.can(actor, "careers.add_note", employee):
        raise CareerError(_("Vous ne pouvez pas ajouter de note à cette fiche."))
    if actor.pk == employee.pk and (kind != FollowUpNote.Kind.WISH or is_private):
        raise CareerError(_("Sur votre fiche, vous pouvez seulement noter un souhait."), "kind")
    note = FollowUpNote.objects.create(
        employee=employee,
        author=actor,
        date=timezone.localdate(),
        kind=kind,
        text=text,
        is_private=is_private,
    )
    audit.log(
        "careers.note_added",
        _("Note ajoutée à la fiche de suivi de %(name)s") % {"name": employee.full_name},
        actor=actor,
        target=employee,
        request=context.request,
    )
    return note


@transaction.atomic
def undo_note(note_id: int, *, context: ActionContext) -> Employee:
    actor = context.person()
    note = FollowUpNote.objects.select_related("employee").filter(pk=note_id, author=actor).first()
    if note is None:
        raise CareerError(_("Cette note a déjà été retirée."))
    employee = note.employee
    note.delete()
    audit.log(
        "careers.note_removed",
        _("Note retirée de la fiche de suivi de %(name)s") % {"name": employee.full_name},
        actor=actor,
        target=employee,
        request=context.request,
    )
    return employee


# ---------- Campagnes (Q1) ----------


@transaction.atomic
def save_campaign(
    data: dict, *, campaign: ReviewCampaign | None = None, context: ActionContext
) -> ReviewCampaign:
    """Crée ou modifie une campagne ; deux campagnes ne se chevauchent pas."""
    overlapping = ReviewCampaign.objects.select_for_update().filter(
        start__lte=data["end"], end__gte=data["start"]
    )
    if campaign is not None:
        overlapping = overlapping.exclude(pk=campaign.pk)
    if overlapping.exists():
        raise CareerError(_("Une campagne couvre déjà cette période."), "start")
    campaign = campaign or ReviewCampaign()
    campaign.label, campaign.start, campaign.end = data["label"], data["start"], data["end"]
    try:
        with transaction.atomic():
            campaign.save()
    except IntegrityError as exc:
        field_name, message = constraints.translate(exc, constraints.INVALID_VALUE)
        raise CareerError(message, field_name) from exc
    audit.log(
        "careers.campaign_saved",
        _("Campagne d'entretiens enregistrée : %(label)s") % {"label": campaign.label},
        actor=context.actor,
        target=campaign,
        request=context.request,
    )
    return campaign


# ---------- Compétences (administration) ----------


def create_default_competencies() -> int:
    """Les 4 compétences par défaut d'une nouvelle entreprise (entreprise courante)."""
    if Competency.objects.exists():
        return 0
    for order, (name, description) in enumerate(DEFAULT_COMPETENCIES, 1):
        Competency.objects.create(name=str(name), description=str(description), order=order)
    return len(DEFAULT_COMPETENCIES)


def _save_competency(competency: Competency, **fields: object) -> None:
    for name, value in fields.items():
        setattr(competency, name, value)
    try:
        with transaction.atomic():
            competency.save()
    except IntegrityError as exc:
        field_name, message = constraints.translate(exc, constraints.INVALID_VALUE)
        raise CareerError(message, field_name) from exc


def _competency_audit(action: str, verb: str, name: str, context: ActionContext) -> None:
    audit.log(
        f"company.competency_{action}",
        _("%(verb)s : %(name)s") % {"verb": verb, "name": name},
        actor=context.actor,
        request=context.request,
    )


@transaction.atomic
def add_competency(name: str, description: str, *, context: ActionContext) -> Competency:
    last = Competency.objects.aggregate(last=Max("order"))["last"] or 0
    competency = Competency()
    _save_competency(competency, name=name, description=description, order=last + 1)
    _competency_audit("added", _("Compétence ajoutée"), name, context)
    return competency


@transaction.atomic
def update_competency(
    competency: Competency, name: str, description: str, *, context: ActionContext
) -> Competency:
    old = competency.name
    _save_competency(competency, name=name, description=description)
    _competency_audit("renamed", _("Compétence modifiée"), f"{old} → {name}", context)
    return competency


@transaction.atomic
def move_competency(competency: Competency, step: int, *, context: ActionContext) -> bool:
    """Échange la compétence avec sa voisine (step = -1 : monter, +1 : descendre). Renvoie
    faux si elle est déjà en tête ou en fin de liste."""
    ordered = list(Competency.objects.select_for_update().order_by("order", "pk"))
    index = next(i for i, c in enumerate(ordered) if c.pk == competency.pk)
    target = index + step
    if not 0 <= target < len(ordered):
        return False
    ordered[index], ordered[target] = ordered[target], ordered[index]
    for position, item in enumerate(ordered, 1):
        if item.order != position:
            Competency.objects.filter(pk=item.pk).update(order=position)
    _competency_audit("moved", _("Compétences réordonnées"), competency.name, context)
    return True


@transaction.atomic
def set_competency_active(
    competency: Competency, active: bool, *, context: ActionContext
) -> Competency:
    """Une compétence désactivée garde ses notes passées et n'est plus demandée."""
    if not active and Competency.objects.filter(active=True).exclude(pk=competency.pk).count() < 1:
        raise CareerError(_("Gardez au moins une compétence active."))
    _save_competency(competency, active=active)
    verb = _("Compétence réactivée") if active else _("Compétence désactivée")
    _competency_audit("enabled" if active else "disabled", verb, competency.name, context)
    return competency


# ---------- Exports PDF (journal sans nom de personne) ----------


def log_review_export(review: Review, *, context: ActionContext) -> None:
    audit.log(
        "careers.review_exported",
        _("Export PDF d'un entretien"),
        actor=context.actor,
        target=review,
        request=context.request,
    )


def log_file_export(employee: Employee, *, context: ActionContext) -> None:
    audit.log(
        "careers.file_exported",
        _("Export PDF d'une fiche de suivi"),
        actor=context.actor,
        target=employee,
        request=context.request,
    )
