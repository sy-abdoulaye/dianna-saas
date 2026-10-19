from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = "apps.core"
    label = "core"
    verbose_name = "Socle"

    def ready(self):
        from django.db.models.signals import m2m_changed

        from apps.core import checks  # noqa: F401
        from apps.core.models import check_m2m_same_company

        m2m_changed.connect(check_m2m_same_company, dispatch_uid="dianna.m2m_same_company")
