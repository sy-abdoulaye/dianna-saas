# CLAUDE.md : Dianna

Dianna est un SaaS B2B multi-entreprise (multi-tenant) de gestion RH et d'organisation du travail, destiné aux PME et ETI françaises (50 à 1 000 salariés). Chaque entreprise cliente dispose d'un espace isolé et active les modules dont elle a besoin.

Ce fichier donne les règles de travail. Le détail est dans `docs/`. Lis `docs/README.md` au début de chaque session, puis la fiche du module concerné dans `docs/modules/`.

## Stack imposée

- Python, Django, PostgreSQL
- Templates Django (rendu serveur), HTML5
- Tailwind CSS (thème dans `static/css/app.css`, construit avec l'outil autonome Tailwind, sans Node en production)
- JavaScript minimal, sans framework (modules ES dans `static/js/`)
- HTMX pour les interactions partielles (filtres, pagination, modales, formulaires)

Les versions exactes et les bibliothèques retenues sont dans `docs/00-decisions.md`. N'ajoute pas de dépendance absente de ce fichier sans le signaler dans ta réponse et l'inscrire dans `docs/00-decisions.md`.

## Règles non négociables

1. **Isolation des entreprises.** Tout modèle métier hérite de `TenantModel` (champ `company`) et passe par `TenantManager`. Aucune requête métier ne doit pouvoir renvoyer les données d'une autre entreprise. Chaque nouvelle vue a un test d'isolation (voir `docs/02-architecture.md`, section Tests). `save()` et le signal `m2m_changed` vérifient que les relations vers un objet métier restent dans la même entreprise ; `QuerySet.update()` et `bulk_create` les contournent : ne les utilise jamais sur une relation vers un objet métier sans vérification explicite de l'entreprise. Pas de queryset sur un modèle métier au niveau d'une classe (attribut queryset d'une vue, champ de formulaire) : toujours dans get_queryset ou __init__.
2. **Permissions côté serveur.** Chaque vue et chaque action vérifie le profil et le périmètre (soi, équipe, entreprise) avec les fonctions de `apps/core/permissions.py`. Masquer un bouton dans le template ne suffit jamais. La matrice fait foi : `docs/04-permissions.md`.
3. **Design system.** Utilise uniquement les jetons et les composants définis dans `docs/05-design-system.md`. Pas de couleur en dur, pas de nouveau composant si un composant existant convient. Le prototype `docs/reference/prototype-dianna.html` est la référence visuelle et comportementale : ouvre-le dans un navigateur pour vérifier un écran.
4. **Accessibilité.** WCAG 2.2 AA : libellé lié à chaque champ, erreurs annoncées, focus visible, navigation clavier, contrastes des jetons respectés.
5. **Données personnelles.** Données RH sensibles : ne journalise jamais de contenu personnel dans les logs applicatifs. Les fichiers (justificatifs, photos) sont privés et servis après contrôle d'accès, par URL signée à durée courte.
6. **Pas de fonctionnalité imaginaire.** N'affiche pas une fonction comme opérationnelle si elle ne l'est pas. Ce qui est prévu plus tard reste masqué ou marqué « Bientôt ».

## Conventions

- Code (modèles, champs, fonctions, URLs internes) en **anglais**. Interface, messages, e-mails et documentation en **français**, via `gettext` / `{% translate %}`.
- Une application Django par domaine dans `apps/` (liste dans `docs/02-architecture.md`).
- Vues basées sur des classes pour le CRUD, fonctions pour les actions HTMX simples. Logique métier dans `services.py` de chaque application, pas dans les vues ni les templates.
- Changements d'état (valider, refuser, envoyer, signer) : une fonction de service par transition, qui vérifie l'état de départ, écrit l'historique, crée la notification et l'entrée du journal d'audit.
- Templates : `templates/<app>/` pour les pages, `templates/<app>/partials/` pour les fragments HTMX, `templates/components/` pour les composants communs.
- Dates : `TIME_ZONE = "Europe/Paris"`, `USE_TZ = True`. Affichage au format français.
- Exports CSV : toujours par `apps/core/csv_export.py` (`csv_content`), qui préfixe d'une apostrophe toute cellule commençant par =, +, -, @, une tabulation ou un retour chariot (injection de formules). Jamais de `csv.writer` direct pour un export.
- Migrations : une migration par changement logique, jamais modifiée une fois fusionnée.

## Commandes

```bash
make up            # démarre PostgreSQL (Docker) et le serveur de développement
make css           # compile Tailwind en mode watch
make test          # pytest (unitaires et intégration)
make e2e           # tests de parcours Playwright
make lint          # ruff check, ruff format --check, djlint
make seed          # charge l'entreprise de démonstration « Exemple SAS »
make migrate
```

Si une commande n'existe pas encore, crée-la dans le `Makefile` au lot 0.

## Façon de travailler

- Travaille **lot par lot** selon `docs/06-plan-de-livraison.md`. Ne commence pas un lot sans que le précédent soit terminé selon sa définition de terminé.
- Avant de coder un module : relis sa fiche, liste les écarts ou ambiguïtés, et pose les questions plutôt que de deviner une règle métier.
- Les points marqués **À confirmer** dans `docs/00-decisions.md` s'appliquent comme décrits tant qu'ils ne sont pas modifiés. Si une implémentation en dépend fortement, signale-le.
- Chaque fonctionnalité livrée l'est avec ses tests (permissions, isolation, règles métier, cas d'erreur).
- Garde les écrans fidèles au prototype : mêmes libellés, mêmes états vides, mêmes messages d'erreur, sauf correction signalée.
- Petits commits explicites en français, au présent (« Ajoute la validation des demandes de télétravail »).
