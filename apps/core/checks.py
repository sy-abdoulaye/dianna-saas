from django.conf import settings
from django.core.checks import Error, register


@register()
def demo_two_factor_switch(app_configs, **kwargs):
    """DEMO_DISABLE_2FA n'est accepté qu'en développement (T-10)."""
    if getattr(settings, "DEMO_DISABLE_2FA", False) and not settings.DEBUG:
        return [
            Error(
                "DEMO_DISABLE_2FA est interdit quand DEBUG est faux.",
                hint="Retirez DEMO_DISABLE_2FA de la configuration de production.",
                id="dianna.E001",
            )
        ]
    return []
