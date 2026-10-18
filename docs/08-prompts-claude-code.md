# Messages à envoyer à Claude Code

Un message par lot. Attendre la note de livraison et vérifier la démo avant de passer au suivant.

## Avant le lot 0 (une seule fois)

> Lis `CLAUDE.md`, puis tout le dossier `docs/`. Ne code rien. Rends-moi : (1) les questions ou contradictions que tu trouves, (2) les points « À confirmer » de `docs/00-decisions.md` qui bloquent le lot 0 ou le lot 1, (3) ton plan détaillé du lot 0.

## Lot 0

> Réalise le lot 0 de `docs/06-plan-de-livraison.md`. Utilise `docs/reference/tokens.css` pour le thème Tailwind et reproduis les composants de `docs/05-design-system.md` à l'identique du prototype `docs/reference/prototype-dianna.html`. Crée la page `/dev/styleguide/`. Termine par la note de livraison.

## Lot 1

> Réalise le lot 1. Commence par `TenantModel`, `TenantManager`, le middleware et la batterie de tests d'isolation, avant toute autre vue. Applique `docs/04-permissions.md` via `apps/core/permissions.py`. Crée `seed_demo` selon `docs/07-donnees-de-demo.md`.

## Lots 2 à 7

> Réalise le lot {n}. Pour chaque module, relis sa fiche dans `docs/modules/`, liste-moi d'abord les écarts avec le prototype ou les ambiguïtés, puis implémente. Chaque critère d'acceptation de la fiche doit avoir son test.

## Lot 8

> Réalise le lot 8. Commence par un audit : liste les risques de sécurité et RGPD restants, classés par gravité, avant de corriger.

## Parcours de bout en bout à automatiser (Playwright)

Repris du prototype, à ajouter au fil des lots :

1. Salarié : déclarer du télétravail depuis le planning ; tenter un troisième jour la même semaine (erreur de quota) ; annuler une demande.
2. Manager : valider une demande depuis l'onglet « À valider », en refuser une autre avec motif ; le salarié voit la notification.
3. Manager puis salarié : entretien individuel complet jusqu'à la clôture et la note dans la fiche de suivi.
4. RH : créer une fiche avec une adresse déjà utilisée (erreur), corriger, archiver, annuler l'archivage.
5. Administrateur : désactiver un module (disparition du menu, page « Module désactivé »), tenter de supprimer un service utilisé.
6. Salarié : répondre à un questionnaire avec un commentaire ; RH : retrouver le commentaire dans les résultats, sans nom.
7. Salarié : compte rendu d'intervention avec deux travaux, envoi ; manager : demande de complément ; salarié : correction et renvoi ; manager : validation.
8. Isolation : un utilisateur de « Autre SA » ne peut ouvrir aucune URL d'« Exemple SAS ».
