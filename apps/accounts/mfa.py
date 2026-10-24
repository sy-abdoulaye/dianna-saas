"""Chiffrement des secrets de double authentification (secret TOTP, graine des codes de
secours) avant leur enregistrement en base, avec MultiFernet pour pouvoir changer de clé."""

from allauth.mfa.adapter import DefaultMFAAdapter

from apps.core import crypto

SETTING = "MFA_ENCRYPTION_KEY"


def fernet():
    return crypto.fernet(SETTING)


class EncryptingMFAAdapter(DefaultMFAAdapter):
    def encrypt(self, text: str) -> str:
        return crypto.encrypt(SETTING, text)

    def decrypt(self, encrypted_text: str) -> str:
        return crypto.decrypt(SETTING, encrypted_text)
