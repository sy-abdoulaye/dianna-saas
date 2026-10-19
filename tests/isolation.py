"""Registre des vues à tester pour l'isolation entre entreprises (règle 1 de CLAUDE.md).

Chaque route de l'espace client qui reçoit un identifiant doit figurer ici : un utilisateur
de l'entreprise A qui ouvre l'URL d'un objet de l'entreprise B reçoit 404, jamais 403.
`test_every_parameterized_route_is_registered` échoue si une nouvelle route est oubliée.

Chaque cas : nom de route → (méthode, fonction qui construit l'URL depuis les données de B).
"""

from django.urls import reverse

ISOLATION_CASES = {
    "core:notification_open": (
        "get",
        lambda b: reverse("core:notification_open", args=[b.notification.pk]),
    ),
    "accounts:invitation": (
        "get",
        lambda b: reverse("accounts:invitation", args=[b.invitation_token]),
    ),
    "accounts:invitation_renew": (
        "post",
        lambda b: reverse("accounts:invitation_renew", args=[b.invitation_token]),
    ),
}

# Routes à paramètre qui ne désignent pas un objet métier d'une entreprise.
NOT_TENANT_OBJECTS = {
    # Clé de réinitialisation d'allauth : elle désigne un compte, pas un objet d'entreprise.
    # Elle n'est acceptée que sur l'hôte où ce compte peut se connecter (TenantUserTokenForm) ;
    # test : test_reset_key_is_refused_on_another_host.
    "account_reset_password_from_key",
    # Guide de style (développement, données fictives).
    "dev:undo",
    "dev:page",
}
