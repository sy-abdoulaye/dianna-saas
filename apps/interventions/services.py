"""Services du suivi d'intervention (docs/modules/11-interventions.md).

- Enregistrer (brouillon, enregistrement automatique, envoi) : seul l'auteur, seulement en
  Brouillon ou Complément demandé ; la version lue par le formulaire doit être la version
  enregistrée, sinon rien n'est écrasé (« modifié dans une autre fenêtre »).
- Envoyer, valider, demander un complément : une fonction par transition, sous verrou, avec
  l'historique (ReportEvent), la notification et le journal ; chacune s'annule dans les 30 s
  tant qu'aucune autre action n'a suivi.
"""

from dataclasses import dataclass, field
from datetime import date

from django.db import IntegrityError, transaction
from django.db.models.functions import Lower
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from apps.core import audit, constraints, notifications
from apps.core.context import ActionContext
from apps.core.dates import format_date
from apps.core.errors import ServiceError
from apps.core.models import Notification
from apps.interventions import selectors
from apps.interventions.models import (
    InterventionReport,
    Mission,
    ReportEvent,
    ReportItem,
    ReportStatus,
)


class ReportError(ServiceError):
    """Refus d'une action sur un compte rendu (message affiché, champ éventuel)."""


STALE = gettext_lazy("Ce compte rendu a été modifié dans une autre fenêtre. Rechargez la page.")
DUPLICATE = gettext_lazy("Un compte rendu existe déjà pour cette intervention et cette période.")
ALREADY_PROCESSED = gettext_lazy("Ce compte rendu a déjà été traité.")
INCOMPLETE = gettext_lazy("Complétez les champs obligatoires avant l'envoi.")
NOT_EDITABLE = gettext_lazy(
    "Ce compte rendu a été envoyé et ne peut plus être modifié, sauf si un complément est demandé."
)
OTHER_DECISION = gettext_lazy("Une autre action a eu lieu depuis. Rien n'a été modifié.")

constraints.register(
    {
        "interventions_one_report_per_period": ("period", DUPLICATE),
        "interventions_extension_after_end": (
            "extension_until",
            gettext_lazy("La prolongation doit aller au-delà de la fin prévue."),
        ),
        "interventions_completion_range": (None, gettext_lazy("Entre 0 et 100.")),
        "interventions_period_first_day": ("period", constraints.INVALID_VALUE),
        "interventions_mission_name_ci_unique": ("mission", constraints.INVALID_VALUE),
    }
)


@dataclass(frozen=True)
class ItemData:
    description: str = ""
    completion: int | None = None
    due_date: date | None = None
    comments: str = ""
    difficulties: str = ""
    solutions: str = ""


@dataclass(frozen=True)
class ReportData:
    mission: str
    period: date
    visibility: str = ""
    planned_end: date | None = None
    extension_wanted: bool = False
    extension_until: date | None = None
    follow_up: str = ""
    done: list[ItemData] = field(default_factory=list)
    next: list[ItemData] = field(default_factory=list)


@dataclass
class Transition:
    """Ce qu'il faut pour annuler immédiatement une transition (jeton signé de 30 s)."""

    report: InterventionReport
    previous_status: str
    previous_note: str
    event_id: int
    notification_ids: list[int] = field(default_factory=list)

    def undo_payload(self) -> dict:
        return {
            "id": str(self.report.public_id),
            "event": self.event_id,
            "previous": self.previous_status,
            "note": self.previous_note,
            "notifications": self.notification_ids,
        }


def report_url(report: InterventionReport) -> str:
    return reverse("interventions:detail", args=[report.public_id])


def _period_label(report: InterventionReport) -> str:
    return format_date(report.period, "month")


def _lock(report: InterventionReport) -> InterventionReport:
    return (
        InterventionReport.objects.select_for_update(of=("self",))
        .select_related("employee", "employee__manager", "mission")
        .get(pk=report.pk)
    )


def _audit(report: InterventionReport, action: str, verb: str, context: ActionContext) -> None:
    summary = _("%(verb)s : compte rendu de %(name)s (%(period)s)") % {
        "verb": verb,
        "name": report.employee.full_name,
        "period": _period_label(report),
    }
    replaced = (
        selectors.replaced_manager(context.actor, report)
        if context.actor is not None and context.actor.pk != report.employee_id
        else None
    )
    if replaced is not None:
        summary += " " + _("(à la place de %(name)s)") % {"name": replaced.full_name}
    audit.log(
        f"interventions.{action}",
        summary,
        actor=context.actor,
        target=report,
        request=context.request,
    )


def _event(report: InterventionReport, context: ActionContext, action: str, comment: str) -> int:
    return ReportEvent.objects.create(
        report=report, actor=context.actor, action=action, comment=comment
    ).pk


# ---------- Enregistrement ----------


def _mission(name: str) -> Mission:
    """Intervention citée : celle de l'entreprise au même nom (sans tenir compte de la casse),
    sinon une nouvelle."""
    found = Mission.objects.annotate(lower=Lower("name")).filter(lower=name.lower()).first()
    if found is not None:
        return found
    try:
        with transaction.atomic():
            return Mission.objects.create(name=name)
    except IntegrityError:
        # Créée au même instant par une autre personne : on reprend la sienne.
        return Mission.objects.annotate(lower=Lower("name")).get(lower=name.lower())


def _write_items(report: InterventionReport, data: ReportData) -> None:
    report.items.all().delete()
    sections = ((ReportItem.Section.DONE, data.done), (ReportItem.Section.NEXT, data.next))
    for section, items in sections:
        for order, item in enumerate(items, 1):
            ReportItem.objects.create(
                report=report,
                section=section,
                order=order,
                description=item.description,
                completion=item.completion,
                due_date=item.due_date,
                comments=item.comments,
                difficulties=item.difficulties if section == ReportItem.Section.DONE else "",
                solutions=item.solutions if section == ReportItem.Section.DONE else "",
            )


def _apply(report: InterventionReport, data: ReportData) -> None:
    report.mission = _mission(data.mission)
    report.period = data.period
    report.visibility = data.visibility
    report.planned_end = data.planned_end
    report.extension_wanted = data.extension_wanted
    report.extension_until = data.extension_until if data.extension_wanted else None
    report.follow_up = data.follow_up


def _editable_for(
    report: InterventionReport, version: int | None, context: ActionContext
) -> InterventionReport:
    actor = context.person()
    report = _lock(report)
    if report.employee_id != actor.pk:
        raise ReportError(_("Seul l'auteur peut modifier ce compte rendu."))
    if not report.is_editable:
        raise ReportError(NOT_EDITABLE)
    if version is not None and version != report.version:
        raise ReportError(STALE)
    return report


@transaction.atomic
def save_report(
    report: InterventionReport | None,
    data: ReportData,
    *,
    version: int | None,
    context: ActionContext,
) -> InterventionReport:
    """Brouillon (clic ou enregistrement automatique). Un nouveau compte rendu est créé ; un
    compte rendu existant n'est enregistré que depuis sa dernière version (`version`)."""
    if report is None:
        report = InterventionReport(employee=context.person())
    else:
        report = _editable_for(report, version, context)
    _apply(report, data)
    if (
        InterventionReport.objects.filter(
            employee=report.employee, mission=report.mission, period=report.period
        )
        .exclude(pk=report.pk)
        .exists()
    ):
        raise ReportError(DUPLICATE, "period")
    report.version = report.version + 1 if report.pk else 1
    try:
        with transaction.atomic():
            report.save()
    except IntegrityError as exc:
        field_name, message = constraints.translate(exc, constraints.INVALID_VALUE)
        raise ReportError(message, field_name) from exc
    _write_items(report, data)
    return report


def missing_for_submission(report: InterventionReport) -> bool:
    """Garde-fou de l'envoi (la page « Modifier » signale chaque champ) : au moins un travail
    réalisé, travaux décrits et chiffrés, visibilité et fin prévue, prolongation datée."""
    items = list(report.items.all())
    done = [i for i in items if i.section == ReportItem.Section.DONE]
    incomplete_item = any(not i.description or i.completion is None for i in items)
    extension = report.extension_wanted and report.extension_until is None
    return (
        not done
        or incomplete_item
        or not report.visibility
        or report.planned_end is None
        or extension
    )


# ---------- Transitions ----------


@transaction.atomic
def submit(
    report: InterventionReport, *, version: int | None = None, context: ActionContext
) -> Transition:
    """Envoi au manager (ou aux RH sans manager) ; le compte rendu n'est plus modifiable."""
    report = _editable_for(report, version, context)
    if missing_for_submission(report):
        raise ReportError(INCOMPLETE)
    previous = report.status
    report.status, report.submitted_at = ReportStatus.SUBMITTED, timezone.now()
    report.version += 1
    report.save(update_fields=["status", "submitted_at", "version", "updated_at"])
    event_id = _event(report, context, ReportEvent.Action.SUBMITTED, "")
    text = _("%(name)s a envoyé son compte rendu d'intervention (%(period)s)") % {
        "name": report.employee.full_name,
        "period": _period_label(report),
    }
    created = notifications.notify_many(
        selectors.validators(report),
        text,
        url=report_url(report),
        kind=Notification.Kind.REQUEST,
        email_subject=_("Compte rendu à valider"),
        source=report,
    )
    _audit(report, "submitted", _("Compte rendu envoyé"), context)
    return Transition(report, previous, report.reviewer_note, event_id, [n.pk for n in created])


@transaction.atomic
def decide(
    report: InterventionReport, *, approve: bool, note: str, context: ActionContext
) -> Transition:
    """Valider (commentaire facultatif) ou demander un complément (remarque obligatoire)."""
    actor = context.person()
    report = _lock(report)
    if report.status != ReportStatus.SUBMITTED:
        raise ReportError(ALREADY_PROCESSED)
    if not selectors.can_decide(actor, report):
        raise ReportError(_("Vous ne pouvez pas traiter ce compte rendu."))
    note = (note or "").strip()
    if not approve and not note:
        raise ReportError(_("Précisez ce qu'il faut compléter."), "note")
    previous_note = report.reviewer_note
    report.status = ReportStatus.APPROVED if approve else ReportStatus.CHANGES_REQUESTED
    report.reviewer_note = note
    report.version += 1
    report.save(update_fields=["status", "reviewer_note", "version", "updated_at"])
    notifications.retract_unsent(report)
    action = ReportEvent.Action.APPROVED if approve else ReportEvent.Action.CHANGES_REQUESTED
    event_id = _event(report, context, action, note)
    text = (
        _("Votre compte rendu de %(period)s est validé")
        if approve
        else _("Un complément est demandé sur votre compte rendu de %(period)s")
    ) % {"period": _period_label(report)}
    created = notifications.notify_many(
        [report.employee],
        text,
        url=report_url(report),
        kind=Notification.Kind.DECISION,
        source=report,
    )
    verb = _("Compte rendu validé") if approve else _("Complément demandé")
    _audit(report, "approved" if approve else "changes_requested", verb, context)
    return Transition(
        report, ReportStatus.SUBMITTED, previous_note, event_id, [n.pk for n in created]
    )


@transaction.atomic
def undo(payload: dict, *, context: ActionContext) -> InterventionReport:
    """Annulation immédiate d'un envoi ou d'une décision par son auteur, seulement si son
    événement est toujours le dernier du compte rendu."""
    actor = context.person()
    report = (
        InterventionReport.objects.select_for_update(of=("self",))
        .select_related("employee", "mission")
        .filter(public_id=payload["id"])
        .first()
    )
    if report is None:
        raise ReportError(ALREADY_PROCESSED)
    last = report.events.order_by("-pk").first()
    if last is None or last.pk != payload["event"] or last.actor_id != actor.pk:
        raise ReportError(OTHER_DECISION)
    Notification.objects.filter(
        pk__in=payload.get("notifications", []),
        source_type="interventionreport",
        source_id=report.pk,
    ).delete()
    report.status, report.reviewer_note = payload["previous"], payload.get("note", "")
    report.version += 1
    if report.status != ReportStatus.SUBMITTED:
        report.submitted_at = None
    report.save()
    if last.action == ReportEvent.Action.SUBMITTED:
        last.delete()  # envoi retiré : le compte rendu redevient un brouillon sans trace d'envoi
    else:
        _event(report, context, ReportEvent.Action.REVERTED, "")
    _audit(report, "reverted", _("Action annulée"), context)
    return report


def log_export(report: InterventionReport, *, context: ActionContext) -> None:
    """Export PDF d'un compte rendu, journalisé sans nom de personne."""
    audit.log(
        "interventions.exported",
        _("Export PDF d'un compte rendu d'intervention"),
        actor=context.actor,
        target=report,
        request=context.request,
    )
