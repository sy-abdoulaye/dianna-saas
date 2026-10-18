# Plan de livraison

Neuf lots, chacun livrable, démontrable et testé. L'ordre suit les dépendances : socle, puis annuaire, puis demandes, puis planning, puis le reste. L'ordre des lots 5 à 7 est **À confirmer**.

## Définition de terminé (pour chaque lot)

- Les écrans correspondent au prototype : mise en page, libellés, états vides, erreurs, clair et sombre, mobile.
- Les permissions de `04-permissions.md` sont appliquées côté serveur et testées pour chaque profil.
- Les tests d'isolation entre entreprises passent pour chaque nouvelle vue.
- Les critères d'acceptation des fiches de modules du lot passent (tests automatisés).
- `make lint` et `make test` passent ; la couverture de `services.py` et `permissions.py` est ≥ 85 %.
- Les données de démonstration couvrent les nouveaux écrans (`make seed`).
- Les décisions prises en cours de lot sont reportées dans `00-decisions.md`.
- Courte note de livraison : ce qui est fait, ce qui reste, les écarts au prototype.

## Lot 0 : fondations

- Projet Django, réglages par environnement, `.env.example`, Docker Compose (PostgreSQL 18), `Makefile`.
- Tailwind v4 avec `reference/tokens.css`, polices auto-hébergées, sprite d'icônes.
- Gabarits `base.html`, mise en page de l'application (menu latéral, barre du haut, tiroir mobile), thème clair/sombre/système.
- Tous les composants communs de `05-design-system.md` et une page `/dev/styleguide/` (développement uniquement) qui les montre.
- HTMX configuré (CSRF, réponses 422 insérées, bandeau d'erreur serveur, événements `toast` et `closeModal`), `ui.js` (menus, modales, notifications), CSP avec nonce.
- Outils qualité, intégration continue, pytest, Playwright.

**Démo :** la page de styleguide en clair et en sombre, sur ordinateur et mobile.

## Lot 1 : socle multi-entreprise et comptes

- `Company`, `CompanyModule`, `Site`, `Service`, `TenantModel`, `TenantManager`, middleware de sous-domaine.
- `User`, `Employee`, connexion par e-mail (allauth), mot de passe oublié, invitation, double authentification pour RH et Admin.
- Profils et `permissions.py`, pages 403, 404 et « Module désactivé ».
- `Notification` (cloche, « Tout marquer comme lu »), `AuditLog`.
- Administration Django réservée à l'éditeur : créer une entreprise, activer des modules, inviter le premier administrateur.
- Commande `seed_demo` (entreprise « Exemple SAS », voir `07-donnees-de-demo.md`).
- Batterie de tests d'isolation réutilisable.

**Démo :** se connecter avec les 4 profils de démonstration ; vérifier qu'une deuxième entreprise est invisible.

## Lot 2 : annuaire et administration

- Fiche `modules/03-annuaire.md` : liste, cartes, recherche, filtres, pagination, fiche à onglets, création, modification, archivage, photo, modification de ses coordonnées, import CSV.
- Fiche `modules/04-administration.md` : entreprise, utilisateurs et profils, services et sites, modules, journal.
- Tableau de bord, version initiale (`modules/02-tableau-de-bord.md`).

## Lot 3 : demandes et validation

- Moteur commun (`approvals/workflow.py`), `CalendarEvent`, notifications et e-mails de demande et de décision.
- Télétravail, congés estivaux (campagne et autres absences), astreintes : `modules/05-demandes.md`.
- Annulation immédiate depuis la notification visuelle.

## Lot 4 : planning et exports

- Vues semaine et mois, filtres, déclaration depuis la grille, jours fériés et fermetures : `modules/06-planning.md`.
- Export CSV, Excel et iCalendar ; export PDF ; exports mensuels RH (télétravail, astreintes) ; synthèse par service de la campagne de congés d'été.
- Tableau de bord complet (présence du jour, à traiter).

**Jalon V1a :** télétravail, congés, astreintes et planning utilisables par un client pilote.

## Lot 5 : transport et matériel

- Justificatifs de transport avec stockage de fichiers privé, relances avant expiration : `modules/05-demandes.md` (section Transport).
- Suivi du matériel : `modules/07-materiel.md`.

## Lot 6 : communication et questionnaires

- Annonces : `modules/08-annonces.md`.
- Questionnaires avec anonymat réel et commentaires par note : `modules/09-questionnaires.md`.

**Jalon V1b :** périmètre V1 du cahier des charges complet.

## Lot 7 : carrière et suivi d'intervention

- Entretiens individuels et professionnels, fiches de suivi, administration des compétences : `modules/10-carriere.md` et `modules/04-administration.md`.
- Comptes rendus d'intervention : `modules/11-interventions.md`.

## Lot 8 : mise en production

- Row Level Security PostgreSQL, revue de la CSP (activée dès le lot 0), limitation des tentatives, en-têtes de sécurité, audit de sécurité externe.
- RGPD : durées de conservation automatiques, export des données d'un salarié et d'une entreprise, suppression à la fin du contrat.
- Préférences de notification, délégation de validation, accès support tracé.
- SSO Google et Microsoft (si confirmé).
- Sauvegardes et restauration testées, supervision, page d'état.
- Audit d'accessibilité, performances (pages < 300 ms côté serveur sur les données de démonstration × 10).

**Jalon commercialisation :** 3 à 5 entreprises pilotes, zéro fuite entre entreprises à l'audit.
