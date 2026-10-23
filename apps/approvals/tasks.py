"""Tâches des demandes, exécutées par le travailleur (django-tasks-db)."""

from datetime import timedelta

from django.db import transaction
from django.tasks import task
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.core.dates import format_date

REMINDER_DAYS = 15


@task
def remind_expiring_transport(company_id: int) -> int:
    """Relance du salarié 15 jours avant la fin d'un abonnement annuel validé (M-06, L5-12) :
    notification et e-mail, une seule fois par justificatif (`reminder_sent_at`, sous verrou :
    deux exécutions simultanées n'envoient qu'une relance)."""
    from apps.approvals.models import RequestStatus, TransportProof
    from apps.core import notifications
    from apps.core.models import Company, CompanyModule, Module
    from apps.core.tenancy import tenant_context

    company = Company.objects.filter(pk=company_id, status=Company.Status.ACTIVE).first()
    if company is None:
        return 0
    sent = 0
    with tenant_context(company):
        # Même règle que l'écran : un module est activé sauf ligne « désactivé ».
        if CompanyModule.objects.filter(module=Module.TRANSPORT, enabled=False).exists():
            return 0
        today = timezone.localdate()
        due = TransportProof.objects.filter(
            ticket_type=TransportProof.TicketType.YEARLY,
            status=RequestStatus.APPROVED,
            reminder_sent_at__isnull=True,
            valid_until__gte=today,
            valid_until__lte=today + timedelta(days=REMINDER_DAYS),
        ).values_list("pk", flat=True)
        for pk in list(due):
            with transaction.atomic():
                proof = (
                    TransportProof.objects.select_for_update(of=("self",))
                    .select_related("requester", "requester__user")
                    .filter(pk=pk, reminder_sent_at__isnull=True)
                    .first()
                )
                if proof is None:
                    continue
                notifications.notify(
                    proof.requester,
                    _(
                        "Votre abonnement annuel de transport se termine le %(day)s. Pensez à "
                        "déposer le justificatif du nouvel abonnement."
                    )
                    % {"day": format_date(proof.valid_until, "long")},
                    url="/transport/",
                    email_subject=_("Votre abonnement de transport se termine bientôt"),
                )
                proof.reminder_sent_at = timezone.now()
                proof.save(update_fields=["reminder_sent_at", "updated_at"])
                sent += 1
    return sent
