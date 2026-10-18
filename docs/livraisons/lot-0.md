# Note de livraison : lot 0, fondations

Date : 18 octobre 2026. Branche : `lot-0`.

## Ce qui est fait

- **Projet.** Django 6.1.2 et Python 3.13 gérés par uv. Réglages `base`, `dev`, `test` et `prod`, fichier `.env.example`. Le modèle `accounts.User` existe dès la première migration (L0-01).
- **Environnement.** PostgreSQL 18 par Docker Compose. `Dockerfile` en deux étapes (Tailwind autonome, puis Gunicorn et WhiteNoise). `Makefile` avec `install`, `up`, `css`, `css-build`, `migrate`, `test`, `e2e`, `lint`, `format`, `check`, `seed` et `shell`.
- **Design system.** `static/css/app.css` reprend les jetons de `tokens.css` à l'identique, avec un repli `prefers-color-scheme` (L0-04). Polices IBM Plex et Schibsted Grotesk auto-hébergées, sprite d'icônes Lucide, HTMX 2.0.11 copié dans le dépôt (L0-07).
- **Gabarits.** `base.html` avec le lien « Aller au contenu », la mise en page de l'application (menu latéral de 264 px, tiroir sous 1 024 px, barre du haut) et la mise en page d'authentification.
- **Composants.** Les 22 composants de `docs/05-design-system.md` sont dans `templates/components/`, avec les balises `{% icon %}`, `{% button %}`, `{% status_badge %}`, `{% control %}`, `{% pagination %}` et `{% theme_switch %}`. La correspondance des statuts est dans `apps/core/status.py`.
- **Comportements.** `static/js/ui.js` gère le thème clair, sombre ou système, le tiroir, les menus, les modales `<dialog>` (focus, Échap, fond, croix, retour du focus) et les notifications (3 au maximum, 5 s ou 8 s, pause au survol). Il gère aussi le bandeau d'erreur serveur ou réseau, la remise à zéro des filtres et la zone de fichier.
- **HTMX côté serveur.** `apps/core/htmx.py` gère les notifications par `HX-Trigger` et la fermeture de modale. `apps/core/undo.py` fournit un jeton d'annulation signé, valable 30 s et réservé à l'auteur (L0-03).
- **Sécurité.** CSP stricte avec nonce, sans `unsafe-inline` ni `unsafe-eval`. Barres en `<progress>` et `<meter>` (L0-02). Cookies `HttpOnly` et `SameSite=Lax`, session de 12 h, HSTS et cookies `Secure` en production. `make check` passe le contrôle `--deploy` de Django.
- **Guide de style.** `/dev/styleguide/` montre chaque composant dans ses états. On y trouve une modale qui répond 422 puis affiche une notification avec « Annuler », des confirmations normale et destructive, les 4 types de notification, une erreur 500 qui conserve la saisie, des filtres et une pagination HTMX dans l'URL, ainsi que les pages d'erreur.
- **Qualité.** ruff, djlint, pre-commit et GitHub Actions (lint, tests, Playwright, image Docker).

## Tests

| Commande | Résultat |
|---|---|
| `make lint` | ruff et djlint sans erreur |
| `make test` | 51 tests, couverture de `apps/` à 94 % |
| `make e2e` | 14 parcours Playwright |
| `make check` | aucune alerte, dont `--deploy` en production |

Il n'y a pas encore de `services.py` ni de `permissions.py` : le seuil de 85 % sur ces fichiers s'appliquera à partir du lot 1.

## Démo

1. `make install`, puis `make up`.
2. Ouvrir http://localhost:8000/dev/styleguide/.
3. Changer le thème dans le menu utilisateur : Clair, Sombre ou Système.
4. Réduire la fenêtre sous 1 024 px pour voir le tiroir.

## Ce qui reste

- **Barre du haut.** Recherche globale, cloche et menu utilisateur ne sont présentés que dans le guide de style. Ils seront branchés aux lots 1 et 2, quand les comptes et les fiches existeront.
- **Thème du compte.** Le choix est mémorisé dans le navigateur. Son enregistrement dans `User.theme` arrive au lot 1.
- **Menu.** Le filtrage par module et par profil arrive au lot 1. Au lot 0, une entrée dont la route n'existe pas encore n'est pas affichée.
- **Intégration continue.** Elle n'a pas encore tourné, faute de dépôt GitHub.
- **Accessibilité automatique.** Le contrôle axe-core est prévu au lot 8. La navigation au clavier est vérifiée par les parcours Playwright.

## Écarts au prototype

- **Icônes.** Le prototype dessinait ses propres tracés, Dianna utilise Lucide comme le prévoit le design system (L0-10).
- **Focus.** L'anneau de focus est un contour de 2 px, comme dans `tokens.css`, au lieu de la double ombre du prototype. Il est visible aussi en mode contraste élevé.
- **Barres de progression.** Ce sont des éléments natifs, au lieu de `<div>` avec style en ligne (L0-02).
- **Onglets.** Ce sont des liens, une URL par onglet (L0-12).
- **Page 404.** Le texte devient « Cette adresse ne correspond à aucune page. », car le prototype disait « … du prototype ».
- **Page 403.** Elle n'affiche pas encore le nom du profil, qui sera ajouté au lot 1.
- **Badge « Validée par le manager ».** Il est ajouté pour M-03 et absent du prototype.
- **Entrées « Bientôt ».** Plan de charge et Recrutement ne sont pas cliquables. La page d'information du prototype attend une décision (fiche socle).
