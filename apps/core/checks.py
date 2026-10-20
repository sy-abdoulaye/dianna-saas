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


ENCRYPTION_SETTINGS = {
    "MFA_ENCRYPTION_KEY": ("dianna.E002", "dianna.E003", "dianna.E004"),
    "TASKS_ENCRYPTION_KEY": ("dianna.E005", "dianna.E006", "dianna.E007"),
}


@register()
def encryption_keys(app_configs, **kwargs):
    """Clés de chiffrement : présentes, valides, distinctes de SECRET_KEY et entre elles."""
    from cryptography.fernet import Fernet

    from apps.core.crypto import parse_keys

    hint = (
        'Générez une clé : python -c "from cryptography.fernet import Fernet; '
        'print(Fernet.generate_key().decode())"'
    )
    errors = []
    seen = {}
    for setting, (missing_id, secret_id, invalid_id) in ENCRYPTION_SETTINGS.items():
        keys = parse_keys(getattr(settings, setting, ""))
        if not keys:
            errors.append(Error(f"{setting} est obligatoire.", hint=hint, id=missing_id))
            continue
        for key in keys:
            if key == settings.SECRET_KEY:
                errors.append(Error(f"{setting} doit être distincte de SECRET_KEY.", id=secret_id))
            if key in seen and seen[key] != setting:
                errors.append(
                    Error(f"{setting} doit être distincte de {seen[key]}.", id="dianna.E008")
                )
            seen[key] = setting
            try:
                Fernet(key.encode())
            except ValueError:
                errors.append(
                    Error(f"{setting} n'est pas une clé Fernet valide.", hint=hint, id=invalid_id)
                )
    return errors
