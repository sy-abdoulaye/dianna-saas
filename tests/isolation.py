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
    # Justificatif de transport (lot 5) : jamais servi pour une autre entreprise.
    "approvals:proof_file": (
        "get",
        lambda b: reverse("approvals:proof_file", args=[b.requests["transport"].public_id]),
    ),
    # Matériel (lot 5) : équipement, signalement et demande de B.
    "equipment:item_detail": (
        "get",
        lambda b: reverse("equipment:item_detail", args=[b.requests["item"].public_id]),
    ),
    "equipment:item_assign": (
        "post",
        lambda b: reverse("equipment:item_assign", args=[b.requests["stock_item"].public_id]),
    ),
    "equipment:item_return": (
        "post",
        lambda b: reverse("equipment:item_return", args=[b.requests["item"].public_id]),
    ),
    "equipment:item_repair": (
        "post",
        lambda b: reverse("equipment:item_repair", args=[b.requests["stock_item"].public_id]),
    ),
    "equipment:item_back": (
        "post",
        lambda b: reverse("equipment:item_back", args=[b.requests["item"].public_id]),
    ),
    "equipment:item_retire": (
        "post",
        lambda b: reverse("equipment:item_retire", args=[b.requests["stock_item"].public_id]),
    ),
    "equipment:issue_new": (
        "get",
        lambda b: reverse("equipment:issue_new", args=[b.requests["item"].public_id]),
    ),
    "equipment:issue_close": (
        "post",
        lambda b: reverse("equipment:issue_close", args=[b.requests["issue"].pk]),
    ),
    "equipment:issue_repair": (
        "post",
        lambda b: reverse("equipment:issue_repair", args=[b.requests["issue"].pk]),
    ),
    "equipment:request_assign": (
        "get",
        lambda b: reverse(
            "equipment:request_assign", args=[b.requests["equipment_request"].public_id]
        ),
    ),
    "approvals:campaign_summary": (
        "get",
        lambda b: reverse("approvals:campaign_summary", args=[b.requests["campaign"].pk]),
    ),
    # Fermetures (lot 4)
    "administration:closure_delete": (
        "get",
        lambda b: reverse("administration:closure_delete", args=[b.requests["closure"].pk]),
    ),
    "approvals:campaign_status": (
        "post",
        lambda b: reverse("approvals:campaign_status", args=[b.requests["campaign"].pk, "clore"]),
    ),
    # Annuaire (lot 2)
    # Communication interne et questionnaires (lot 6).
    "announcements:detail": (
        "get",
        lambda b: reverse("announcements:detail", args=[b.requests["announcement"].public_id]),
    ),
    "announcements:edit": (
        "post",
        lambda b: reverse("announcements:edit", args=[b.requests["announcement"].public_id]),
    ),
    "announcements:pin": (
        "post",
        lambda b: reverse("announcements:pin", args=[b.requests["announcement"].public_id]),
    ),
    "announcements:delete": (
        "post",
        lambda b: reverse("announcements:delete", args=[b.requests["announcement"].public_id]),
    ),
    "surveys:detail": (
        "get",
        lambda b: reverse("surveys:detail", args=[b.requests["survey"].public_id]),
    ),
    "surveys:answer": (
        "post",
        lambda b: reverse("surveys:answer", args=[b.requests["survey"].public_id]),
    ),
    "surveys:edit": (
        "post",
        lambda b: reverse("surveys:edit", args=[b.requests["draft_survey"].public_id]),
    ),
    "surveys:publish": (
        "post",
        lambda b: reverse("surveys:publish", args=[b.requests["draft_survey"].public_id]),
    ),
    "surveys:close": (
        "post",
        lambda b: reverse("surveys:close", args=[b.requests["survey"].public_id]),
    ),
    "surveys:delete": (
        "post",
        lambda b: reverse("surveys:delete", args=[b.requests["draft_survey"].public_id]),
    ),
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
    "approvals:export",
    # Annulation d'une attribution : jeton signé lié à l'auteur ; l'équipement est relu dans
    # l'entreprise courante (test : test_undo_token_of_another_company_is_refused, matériel).
    "equipment:undo",
    # Annulation immédiate : jeton signé lié à l'auteur, demande relue dans l'entreprise
    # courante (test : test_undo_token_of_another_company_is_refused).
    "approvals:undo",
    # Modules : le paramètre est le code du module, pas un objet d'une entreprise.
    "administration:toggle_module",
    # Annulation d'une suppression d'annonce : jeton signé lié à l'auteur ; l'annonce est
    # relue dans l'entreprise courante (test : test_undo_token_of_another_company_is_refused,
    # annonces).
    "announcements:undo",
}
