from django.apps import AppConfig


class CareersConfig(AppConfig):
    name = "apps.careers"
    label = "careers"
    verbose_name = "Carrière et évaluations"

    def ready(self):
        """E-mail d'un entretien : ne part pas si l'entretien a été retiré entre-temps."""
        from apps.careers.models import Review
        from apps.core import notifications

        notifications.register_source("review", lambda pk: Review.objects.filter(pk=pk).exists())
