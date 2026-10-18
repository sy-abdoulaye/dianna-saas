from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = "apps.core"
    label = "core"
    verbose_name = "Socle"

    def ready(self):
        from apps.core import checks  # noqa: F401
