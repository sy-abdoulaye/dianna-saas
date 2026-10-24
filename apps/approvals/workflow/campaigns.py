"""Campagnes de congés d'été gérées par les RH (L3-15).

Les fonctions du paquet s'appellent par la façade `workflow` (apps/approvals/workflow/
__init__.py) : point d'entrée unique, et point de remplacement des tests."""

from django.db import IntegrityError, transaction
from django.utils.translation import gettext as _

from apps.approvals import workflow
from apps.approvals.models import (
    SummerCampaign,
)
from apps.core import audit

CAMPAIGN_FIELDS = ("label", "period_start", "period_end", "deadline", "conflict_threshold")


@transaction.atomic
def create_summer_campaign(data: dict, actor, *, http_request=None):
    """Crée une campagne en brouillon et l'inscrit au journal d'audit."""
    campaign = SummerCampaign.objects.create(
        **{name: data[name] for name in workflow.CAMPAIGN_FIELDS if name in data}
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
def open_summer_campaign(campaign, actor, *, http_request=None):
    """Ouvre une campagne. Toutes les campagnes de l'entreprise sont verrouillées : deux
    ouvertures simultanées donnent une seule campagne ouverte (A3-06)."""
    campaigns = {c.pk: c for c in SummerCampaign.objects.select_for_update().order_by("pk")}
    campaign = campaigns.get(campaign.pk)
    if campaign is None or campaign.status != SummerCampaign.Status.DRAFT:
        raise workflow.WorkflowError(_("Cette campagne ne peut pas être ouverte."))
    if any(c.status == SummerCampaign.Status.OPEN for c in campaigns.values()):
        raise workflow.WorkflowError(workflow.CAMPAIGN_ALREADY_OPEN)
    campaign.status = SummerCampaign.Status.OPEN
    try:
        with transaction.atomic():
            campaign.save(update_fields=["status", "updated_at"])
    except IntegrityError as exc:
        raise workflow.WorkflowError(workflow.CAMPAIGN_ALREADY_OPEN) from exc
    workflow._campaign_audit(campaign, actor, _("Campagne ouverte"), http_request)
    return campaign


@transaction.atomic
def close_summer_campaign(campaign, actor, *, http_request=None):
    campaign = SummerCampaign.objects.select_for_update().filter(pk=campaign.pk).first()
    if campaign is None or campaign.status != SummerCampaign.Status.OPEN:
        raise workflow.WorkflowError(_("Cette campagne n'est pas ouverte."))
    campaign.status = SummerCampaign.Status.CLOSED
    campaign.save(update_fields=["status", "updated_at"])
    workflow._campaign_audit(campaign, actor, _("Campagne close"), http_request)
    return campaign


def _campaign_audit(campaign, actor, title, http_request):
    audit.log(
        f"requests.campaign_{campaign.status}",
        f"{title} : {campaign.label}",
        actor=actor,
        target=campaign,
        request=http_request,
    )
