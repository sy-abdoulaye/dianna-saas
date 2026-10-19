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


@register()
def mfa_encryption_key(app_configs, **kwargs):
    """Clé de chiffrement des secrets TOTP : présente, valide, distincte de SECRET_KEY."""
    from cryptography.fernet import Fernet

    from apps.accounts.mfa import parse_keys

    keys = parse_keys(getattr(settings, "MFA_ENCRYPTION_KEY", ""))
    hint = (
        'Générez une clé : python -c "from cryptography.fernet import Fernet; '
        'print(Fernet.generate_key().decode())"'
    )
    if not keys:
        return [Error("MFA_ENCRYPTION_KEY est obligatoire.", hint=hint, id="dianna.E002")]
    errors = []
    for key in keys:
        if key == settings.SECRET_KEY:
            errors.append(
                Error("MFA_ENCRYPTION_KEY doit être distincte de SECRET_KEY.", id="dianna.E003")
            )
        try:
            Fernet(key.encode())
        except ValueError:
            errors.append(
                Error(
                    "MFA_ENCRYPTION_KEY n'est pas une clé Fernet valide.",
                    hint=hint,
                    id="dianna.E004",
                )
            )
    return errors
