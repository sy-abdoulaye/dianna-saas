from django.apps import AppConfig


class AnnouncementsConfig(AppConfig):
    name = "apps.announcements"
    label = "announcements"
    verbose_name = "Communication interne"

    def ready(self):
        """E-mail d'une annonce : ne part pas si l'annonce a été supprimée (L6-18)."""
        from apps.announcements import selectors
        from apps.core import notifications

        notifications.register_source(
            "announcement", lambda pk: selectors.visible().filter(pk=pk).exists()
        )
