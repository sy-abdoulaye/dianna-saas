"""Chiffrement symétrique avec rotation de clés (MultiFernet).

Une clé par usage, chacune distincte de SECRET_KEY :
- MFA_ENCRYPTION_KEY : secrets de double authentification (A1-02) ;
- TASKS_ENCRYPTION_KEY : arguments des tâches qui portent un e-mail d'allauth (A3-04).
Plusieurs clés séparées par des virgules : la première chiffre, toutes déchiffrent."""

from functools import lru_cache

from cryptography.fernet import Fernet, MultiFernet
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def parse_keys(value: str) -> list[str]:
    return [key.strip() for key in (value or "").split(",") if key.strip()]


@lru_cache(maxsize=8)
def _fernet(value: str, setting: str) -> MultiFernet:
    keys = parse_keys(value)
    if not keys:
        raise ImproperlyConfigured(f"{setting} est obligatoire.")
    return MultiFernet([Fernet(key.encode()) for key in keys])


def fernet(setting: str) -> MultiFernet:
    return _fernet(getattr(settings, setting, ""), setting)


def encrypt(setting: str, text: str) -> str:
    return fernet(setting).encrypt(text.encode()).decode()


def decrypt(setting: str, token: str) -> str:
    return fernet(setting).decrypt(token.encode()).decode()
