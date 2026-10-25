"""Contrôles métier qui dépendent des autres demandes du demandeur (A3-02).

Les fonctions du paquet s'appellent par la façade `workflow` (apps/approvals/workflow/
__init__.py) : point d'entrée unique, et point de remplacement des tests."""

from decimal import Decimal

from django.utils.translation import gettext as _

from apps.agenda.days import day_off, day_off_message
from apps.approvals import rules
from apps.approvals.models import (
    ACTIVE_STATUSES,
    LeaveRequest,
    OnCallDeclaration,
    RequestStatus,
    SummerCampaign,
    TeleworkRequest,
    TransportProof,
)
from apps.approvals.workflow.common import AMOUNT_RANGE, SAME_DAY
from apps.core.dates import format_date


def check_request(request, *, campaign=None) -> dict:
    """Contrôles qui dépendent des autres demandes du demandeur. Renvoie {champ: message}
    (vide si tout va bien). `request` peut ne pas être enregistrée (envoi) ; si elle l'est,
    elle est exclue des comptes (annulation immédiate)."""
    if isinstance(request, TeleworkRequest):
        return _check_telework(request)
    if isinstance(request, LeaveRequest):
        return _check_leave(request, campaign)
    if isinstance(request, TransportProof):
        return _check_transport(request)
    if isinstance(request, OnCallDeclaration):
        return _check_on_call(request)
    return {}


def _check_telework(request) -> dict:
    """Jour non férié ni fermé (T-16, L3-12), une seule demande par jour, quota de la
    semaine."""
    requester, pk = request.requester, request.pk
    off = day_off(request.date, requester.site_id)
    if off is not None:
        return {"date": day_off_message(request.date, off)}
    same_day = TeleworkRequest.objects.filter(
        requester=requester,
        date=request.date,
        status__in=(RequestStatus.PENDING, RequestStatus.APPROVED),
    ).exclude(pk=pk)
    if same_day.exists():
        return {"date": SAME_DAY}
    quota = rules.weekly_quota(requester)
    used = rules.telework_days_in_week(requester, request.date, exclude_pk=pk)
    if used < quota:
        return {}
    return {
        "date": _(
            "Vous avez déjà %(n)s jours de télétravail la semaine du %(week)s (maximum %(quota)s)."
        )
        % {
            "n": used,
            "week": format_date(rules.monday_of(request.date), "short"),
            "quota": quota,
        }
    }


def _check_leave(request, campaign) -> dict:
    """Congés d'été : campagne ouverte et période comprise dans la sienne ; tout congé : pas
    de chevauchement avec une autre demande."""
    if request.leave_type == LeaveRequest.LeaveType.SUMMER:
        errors = _check_summer_campaign(request, campaign)
        if errors:
            return errors
    if rules.leave_overlaps(request.requester, request.start, request.end, exclude_pk=request.pk):
        return {"start": _("Cette période chevauche une de vos demandes existantes.")}
    return {}


def _check_summer_campaign(request, campaign) -> dict:
    if campaign is None or campaign.status != SummerCampaign.Status.OPEN:
        return {
            "leave_type": _(
                "Aucune campagne de congés d'été n'est ouverte : choisissez « Autre absence »."
            )
        }
    if request.start < campaign.period_start or request.end > campaign.period_end:
        return {
            "start": _(
                "Les congés d'été de la campagne %(label)s sont compris entre le %(a)s et le %(b)s."
            )
            % {
                "label": campaign.label,
                "a": format_date(campaign.period_start, "long"),
                "b": format_date(campaign.period_end, "long"),
            }
        }
    return {}


def _check_on_call(request) -> dict:
    if request.kind == OnCallDeclaration.Kind.ON_CALL and rules.on_call_overlaps(
        request.requester, request.start, request.end, exclude_pk=request.pk
    ):
        return {"start": _("Cette astreinte chevauche une de vos astreintes déclarées.")}
    return {}


SUBSCRIPTIONS = (TransportProof.TicketType.MONTHLY, TransportProof.TicketType.YEARLY)


def _check_transport(request) -> dict:
    """Mois dans la fenêtre acceptée (L5-07), montant dans ses bornes, et pas de chevauchement
    entre deux abonnements actifs (mensuel ou annuel, L5-06) ; un titre unique reste toujours
    possible. Contrôles du service (A3-02), refaits même si le formulaire les a déjà faits."""
    from apps.approvals.forms import transport_months

    first, last = transport_months()
    if request.month is None or not first <= request.month.replace(day=1) <= last:
        return {
            "month": _("Choisissez un mois entre %(a)s et %(b)s.")
            % {"a": format_date(first, "month"), "b": format_date(last, "month")}
        }
    if request.amount is None or not Decimal("0") < Decimal(request.amount) <= Decimal("1000"):
        return {"amount": AMOUNT_RANGE}
    if request.ticket_type not in SUBSCRIPTIONS:
        return {}
    request.compute_validity()
    overlapping = (
        TransportProof.objects.filter(
            requester=request.requester,
            ticket_type__in=SUBSCRIPTIONS,
            status__in=ACTIVE_STATUSES,
            month__lte=request.valid_until,
            valid_until__gte=request.month,
        )
        .exclude(pk=request.pk)
        .order_by("month")
        .first()
    )
    if overlapping is None:
        return {}
    covered = max(overlapping.month, request.month)
    return {
        "month": _("Un justificatif de ce type couvre déjà %(month)s.")
        % {"month": format_date(covered, "month")}
    }
