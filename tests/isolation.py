"""Registre des vues à tester pour l'isolation entre entreprises (règle 1 de CLAUDE.md).

Chaque route de l'espace client qui reçoit un identifiant doit figurer ici : un utilisateur
de l'entreprise A qui ouvre l'URL d'un objet de l'entreprise B reçoit 404, jamais 403.
`test_every_parameterized_route_is_registered` échoue si une nouvelle route est oubliée.

Chaque cas : nom de route → (méthode, fonction qui construit l'URL depuis les données de B).
"""

from django.urls import reverse

ISOLATION_CASES = {
    # Demandes (lot 3) : une demande de B ouverte par un administrateur de A.
    "approvals:detail": (
        "get",
        lambda b: reverse("approvals:detail", args=["telework", b.requests["telework"].public_id]),
    ),
    "approvals:approve": (
        "post",
        lambda b: reverse("approvals:approve", args=["leave", b.requests["leave"].public_id]),
    ),
    "approvals:refuse": (
        "get",
        lambda b: reverse("approvals:refuse", args=["telework", b.requests["telework"].public_id]),
    ),
    "approvals:cancel": (
        "post",
        lambda b: reverse("approvals:cancel", args=["on_call", b.requests["on_call"].public_id]),
    ),
    "approvals:cancel_approved": (
        "get",
        lambda b: reverse(
            "approvals:cancel_approved", args=["telework", b.requests["telework"].public_id]
        ),
    ),
    "approvals:campaign_status": (
        "post",
        lambda b: reverse("approvals:campaign_status", args=[b.requests["campaign"].pk, "clore"]),
    ),
    # Annuaire (lot 2)
    "people:detail": ("get", lambda b: reverse("people:detail", args=[b.employee.public_id])),
    "people:edit": ("get", lambda b: reverse("people:edit", args=[b.employee.public_id])),
    "people:archive": ("get", lambda b: reverse("people:archive", args=[b.employee.public_id])),
    "people:reactivate": (
        "post",
        lambda b: reverse("people:reactivate", args=[b.employee.public_id]),
    ),
    # Administration (lot 2)
    "administration:change_role": (
        "get",
        lambda b: reverse("administration:change_role", args=[b.employee.public_id]) + "?role=hr",
    ),
    "administration:send_invitation": (
        "post",
        lambda b: reverse("administration:send_invitation", args=[b.pending.public_id]),
    ),
    "administration:structure_rename": (
        "get",
        lambda b: reverse("administration:structure_rename", args=["services", b.service.pk]),
    ),
    "administration:structure_delete": (
        "get",
        lambda b: reverse("administration:structure_delete", args=["sites", b.site.pk]),
    ),
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
    # Fichiers privés : le jeton signé porte l'entreprise, refusé sur un autre hôte
    # (test : test_private_file_is_refused_on_another_company_host).
    "core:private_file",
    # Annulation d'archivage : jeton signé lié à l'auteur ; la fiche est relue dans
    # l'entreprise courante (test : test_undo_archive_of_another_company_is_refused).
    "people:undo",
    # Ajout d'un service ou d'un site : le paramètre est le type (« services », « sites »).
    "administration:structure_add",
    # Demandes : le paramètre est le type (teletravail, conges, astreintes).
    "approvals:list",
    "approvals:new",
    # Annulation immédiate : jeton signé lié à l'auteur, demande relue dans l'entreprise
    # courante (test : test_undo_token_of_another_company_is_refused).
    "approvals:undo",
    # Modules : le paramètre est le code du module, pas un objet d'une entreprise.
    "administration:toggle_module",
}
