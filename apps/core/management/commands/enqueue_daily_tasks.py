"""Tâches quotidiennes mises en file pour le travailleur (L5-12) : relance des abonnements de
transport. Lancée chaque jour par le service `scheduler` (docker-compose.yml, profil taches) ;
en production, au lot 8."""

from django.core.management.base import BaseCommand

from apps.core.models import Company


class Command(BaseCommand):
    help = "Met en file les tâches quotidiennes (relance des abonnements de transport)."

    def handle(self, *args, **options):
        from apps.approvals.tasks import remind_expiring_transport

        companies = list(
            Company.objects.filter(status=Company.Status.ACTIVE).values_list("pk", flat=True)
        )
        for company_id in companies:
            remind_expiring_transport.enqueue(company_id)
        self.stdout.write(f"Tâches quotidiennes mises en file : {len(companies)} entreprise(s).")
