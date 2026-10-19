"""Chiffrement des secrets de double authentification (secret TOTP, graine des codes de
secours) avant leur enregistrement en base, avec MultiFernet pour pouvoir changer de clé."""

from functools import lru_cache

from allauth.mfa.adapter import DefaultMFAAdapter
from cryptography.fernet import Fernet, MultiFernet
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def parse_keys(value: str) -> list[str]:
    return [key.strip() for key in (value or "").split(",") if key.strip()]


@lru_cache(maxsize=4)
def _fernet(value: str) -> MultiFernet:
    keys = parse_keys(value)
    if not keys:
        raise ImproperlyConfigured("MFA_ENCRYPTION_KEY est obligatoire.")
    return MultiFernet([Fernet(key.encode()) for key in keys])


def fernet() -> MultiFernet:
    return _fernet(settings.MFA_ENCRYPTION_KEY)


class EncryptingMFAAdapter(DefaultMFAAdapter):
    def encrypt(self, text: str) -> str:
        return fernet().encrypt(text.encode()).decode()

    def decrypt(self, encrypted_text: str) -> str:
        return fernet().decrypt(encrypted_text.encode()).decode()
