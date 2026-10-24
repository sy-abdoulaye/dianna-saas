"""Tâches quotidiennes mises en file pour le travailleur : relance des abonnements de
transport (L5-12), clôture des questionnaires échus (L6-06). Lancée chaque jour par le
service `scheduler` (docker-compose.yml, profil taches) ; en production, au lot 8."""

from django.core.management.base import BaseCommand

from apps.core.models import Company


class Command(BaseCommand):
    help = "Met en file les tâches quotidiennes (relance du transport, questionnaires échus)."

    def handle(self, *args, **options):
        from apps.approvals.tasks import remind_expiring_transport
        from apps.surveys.tasks import close_expired_surveys

        companies = list(
            Company.objects.filter(status=Company.Status.ACTIVE).values_list("pk", flat=True)
        )
        for company_id in companies:
            remind_expiring_transport.enqueue(company_id)
            close_expired_surveys.enqueue(company_id)
        self.stdout.write(f"Tâches quotidiennes mises en file : {len(companies)} entreprise(s).")
