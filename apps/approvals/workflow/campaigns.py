"""Campagnes de congés d'été gérées par les RH (L3-15).

Les modules du paquet s'importent directement entre eux ; le reste de l'application passe
par la façade `workflow` (apps/approvals/workflow/__init__.py)."""

from django.db import IntegrityError, transaction
from django.utils.translation import gettext as _

from apps.approvals.models import (
    SummerCampaign,
)
from apps.approvals.workflow.common import CAMPAIGN_ALREADY_OPEN, WorkflowError
from apps.core import audit
from apps.core.context import ActionContext

CAMPAIGN_FIELDS = ("label", "period_start", "period_end", "deadline", "conflict_threshold")


@transaction.atomic
def create_summer_campaign(data: dict, *, context: ActionContext) -> SummerCampaign:
    """Crée une campagne en brouillon et l'inscrit au journal d'audit."""
    actor, http_request = context.person(), context.request
    campaign = SummerCampaign.objects.create(
        **{name: data[name] for name in CAMPAIGN_FIELDS if name in data}
    )
    audit.log(
        "requests.campaign_created",
        _("Campagne créée : %(l)s") % {"l": campaign.label},
        actor=actor,
        target=campaign,
        request=http_request,
    )
    return campaign


@transaction.atomic
def open_summer_campaign(campaign: SummerCampaign, *, context: ActionContext) -> SummerCampaign:
    """Ouvre une campagne. Toutes les campagnes de l'entreprise sont verrouillées : deux
    ouvertures simultanées donnent une seule campagne ouverte (A3-06)."""
    context.person()
    campaigns = {c.pk: c for c in SummerCampaign.objects.select_for_update().order_by("pk")}
    locked = campaigns.get(campaign.pk)
    if locked is None or locked.status != SummerCampaign.Status.DRAFT:
        raise WorkflowError(_("Cette campagne ne peut pas être ouverte."))
    if any(c.status == SummerCampaign.Status.OPEN for c in campaigns.values()):
        raise WorkflowError(CAMPAIGN_ALREADY_OPEN)
    locked.status = SummerCampaign.Status.OPEN
    try:
        with transaction.atomic():
            locked.save(update_fields=["status", "updated_at"])
    except IntegrityError as exc:
        raise WorkflowError(CAMPAIGN_ALREADY_OPEN) from exc
    _campaign_audit(locked, _("Campagne ouverte"), context)
    return locked


@transaction.atomic
def close_summer_campaign(campaign: SummerCampaign, *, context: ActionContext) -> SummerCampaign:
    context.person()
    campaign = SummerCampaign.objects.select_for_update().filter(pk=campaign.pk).first()
    if campaign is None or campaign.status != SummerCampaign.Status.OPEN:
        raise WorkflowError(_("Cette campagne n'est pas ouverte."))
    campaign.status = SummerCampaign.Status.CLOSED
    campaign.save(update_fields=["status", "updated_at"])
    _campaign_audit(campaign, _("Campagne close"), context)
    return campaign


def _campaign_audit(campaign: SummerCampaign, title: str, context: ActionContext) -> None:
    audit.log(
        f"requests.campaign_{campaign.status}",
        f"{title} : {campaign.label}",
        actor=context.actor,
        target=campaign,
        request=context.request,
    )
