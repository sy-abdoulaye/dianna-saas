"""Purge des résultats de tâches (A3-04) : tâches réussies restantes, et échecs de plus de
7 jours. Planifiée une fois par jour (service `scheduler` de docker-compose.yml)."""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.tasks import TaskResultStatus
from django.utils import timezone
from django_tasks_db.models import DBTaskResult

from apps.core.ratelimit import purge_expired

FAILED_RETENTION_DAYS = 7


class Command(BaseCommand):
    help = (
        "Supprime les résultats de tâches terminées (réussies, ou échouées depuis 7 jours) "
        "et les compteurs de limite de fréquence expirés."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=FAILED_RETENTION_DAYS,
            help="Conservation des échecs, en jours (7 par défaut).",
        )

    def handle(self, *args, days=FAILED_RETENTION_DAYS, **options):
        limit = timezone.now() - timedelta(days=days)
        successful, _ = DBTaskResult.objects.filter(status=TaskResultStatus.SUCCESSFUL).delete()
        failed, _ = DBTaskResult.objects.filter(
            status=TaskResultStatus.FAILED, finished_at__lt=limit
        ).delete()
        counters = purge_expired()
        self.stdout.write(
            f"Résultats supprimés : {successful} réussis, {failed} en échec. "
            f"Compteurs de limite expirés : {counters}."
        )
