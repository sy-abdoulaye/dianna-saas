# CLAUDE.md : Dianna

**Langue.** Toutes les réponses à Leo, les notes de livraison, la documentation, les descriptions de demandes de fusion et les messages de commit sont en français (commits au présent). Seuls les noms dans le code (variables, fonctions, classes, branches) restent en anglais.

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

1. **Isolation des entreprises.** Tout modèle métier hérite de `TenantModel` (champ `company`) et passe par `TenantManager` ; seules les réponses anonymes aux questionnaires héritent de `TenantBase` (même isolation, sans horodatage, L6-12). Aucune requête métier ne doit pouvoir renvoyer les données d'une autre entreprise. Chaque nouvelle vue a un test d'isolation (voir `docs/02-architecture.md`, section Tests). `save()` et le signal `m2m_changed` vérifient que les relations vers un objet métier restent dans la même entreprise ; `QuerySet.update()` et `bulk_create` les contournent : ne les utilise jamais sur une relation vers un objet métier sans vérification explicite de l'entreprise. Pas de queryset sur un modèle métier au niveau d'une classe (attribut queryset d'une vue, champ de formulaire) : toujours dans get_queryset ou __init__.
2. **Permissions côté serveur.** Chaque vue et chaque action vérifie le profil et le périmètre (soi, équipe, entreprise) avec les fonctions de `apps/core/permissions.py`. Masquer un bouton dans le template ne suffit jamais. La matrice fait foi : `docs/04-permissions.md`.
3. **Design system.** Utilise uniquement les jetons et les composants définis dans `docs/05-design-system.md`. Pas de couleur en dur, pas de nouveau composant si un composant existant convient. Le prototype `docs/reference/prototype-dianna.html` est la référence visuelle et comportementale : ouvre-le dans un navigateur pour vérifier un écran.
4. **Accessibilité.** WCAG 2.2 AA : libellé lié à chaque champ, erreurs annoncées, focus visible, navigation clavier, contrastes des jetons respectés.
5. **Données personnelles.** Données RH sensibles : ne journalise jamais de contenu personnel dans les logs applicatifs. Les fichiers sont privés et servis après contrôle d'accès : photos et logos par URL signée à durée courte (A2-07) ; un justificatif jamais par lien signé, seulement par la vue qui contrôle la permission à chaque téléchargement (L5-01).
6. **Pas de fonctionnalité imaginaire.** N'affiche pas une fonction comme opérationnelle si elle ne l'est pas. Ce qui est prévu plus tard reste masqué ou marqué « Bientôt ».

## Conventions

- Code (modèles, champs, fonctions, URLs internes) en **anglais**. Interface, messages, e-mails et documentation en **français**, via `gettext` / `{% translate %}`.
- Une application Django par domaine dans `apps/` (liste dans `docs/02-architecture.md`).
- Vues basées sur des classes pour le CRUD, fonctions pour les actions HTMX simples. Logique métier dans `services.py` de chaque application, pas dans les vues ni les templates.
- Changements d'état (valider, refuser, envoyer, signer) : une fonction de service par transition, qui vérifie l'état de départ, écrit l'historique, crée la notification et l'entrée du journal d'audit.
- Templates : `templates/<app>/` pour les pages, `templates/<app>/partials/` pour les fragments HTMX, `templates/components/` pour les composants communs.
- Texte saisi : les caractères de contrôle et de mise en forme bidirectionnelle sont retirés par `apps/core/text.strip_unsafe_characters`, branché sur tous les `forms.CharField` (L6-19). Toute saisie qui ne passe pas par un formulaire (fichier importé, API) l'appelle explicitement.
- Dates : `TIME_ZONE = "Europe/Paris"`, `USE_TZ = True`. Affichage au format français, toujours par `apps/core/dates.format_date` (filtre `fr_date`) : « 1er novembre », « mer. 21 oct. » ; jamais `|date:` ni `date_format` directs pour une date affichée (L5-22).
- Nombres décimaux saisis : toujours `apps/core/fields.DecimalTextField` (texte, `inputmode="decimal"`, virgule ou point), jamais `type="number"` (L5-20).
- Exports CSV : toujours par `apps/core/csv_export.py` (`csv_content`), qui préfixe d'une apostrophe toute cellule commençant par =, +, -, @, une tabulation ou un retour chariot (injection de formules). Jamais de `csv.writer` direct pour un export. Excel : toujours par `apps/core/xlsx_export.py` (même neutralisation, cellules texte enregistrées comme texte). PDF : toujours par `apps/core/pdf.py` (récupérateur d'URL fermé : jamais de `weasyprint.HTML` direct). Chaque export vérifie le périmètre côté serveur et s'inscrit au journal d'audit sans nom de personne.
- Contrôles métier (A3-02) : les vérifications qui dépendent d'autres données (quota, doublon, chevauchement, période) et les verrous (`select_for_update`) sont dans le service, jamais dans la vue ni dans le formulaire ; le formulaire ne vérifie que ses champs, la vue appelle le service et affiche ses erreurs. Une `IntegrityError` devient un message, jamais une erreur 500. Seule exception : `seed_demo` crée sans `check_request` les demandes de démonstration déjà passées (dates antérieures au jour du chargement).
- E-mails (A3-04) : toujours par `apps/core/mail.py`, donc par une tâche ; aucune donnée sensible en clair dans les arguments d'une tâche (identifiants seulement, ou contenu chiffré avec `TASKS_ENCRYPTION_KEY`).
- Planning et compteurs : règle de confidentialité L4-16 appliquée par une seule fonction, partout (vue, aperçu, exports, compteurs, tableau de bord).
- Toute limite de fréquence passe par apps/core/ratelimit.py, jamais par le cache.
- Fichiers déposés : type réel vérifié par `apps/core/files.clean_document` ; stockés sous `<company_id>/…` avec un nom aléatoire (jamais le nom d'origine) ; un justificatif est servi par `serve_isolated` après contrôle de la permission, jamais par lien signé.
- Écriture d'un fichier (justificatif, photo, logo et tout futur dépôt) : son nom est inscrit dans la liste de nettoyage avant toute écriture dans le stockage, le fichier est écrit explicitement avant l'INSERT ou l'UPDATE, et il est supprimé si l'opération échoue (`apps/core/files.file_writes`, `workflow.submit`) ; l'ancien fichier remplacé n'est supprimé qu'après la validation de la transaction. Jamais de `FieldFile.save()` direct dans un service. Une panne du stockage (`StorageUnavailableError`) donne un message, jamais une erreur 500.
- Migrations : une migration par changement logique, jamais modifiée une fois fusionnée (seule exception, sans effet sur le schéma : L5-25).

## Qualité du code

- Logique métier dans `services.py`, lectures complexes (filtres, périmètres, agrégats) dans `selectors.py`, vues minces : elles lisent la requête, appellent un service ou un sélecteur, rendent la réponse.
- Une fonction fait une chose. ruff le vérifie (`pyproject.toml`) : complexité ≤ 10, 6 `return`, 12 branches, 6 arguments, 50 instructions au plus (RUF100 signale un `noqa` devenu inutile). Un `noqa` n'est admis qu'avec sa raison sur la même ligne.
- Pas de duplication : réutiliser les briques existantes au lieu de les recopier :
  - jeton d'annulation (`apps/core/undo.py`) et confirmation (`components/confirm.html`) ;
  - notifications (`apps/core/notifications.py`), journal (`apps/core/audit.py`), e-mails (`apps/core/mail.py`) ;
  - exports (`csv_export`, `xlsx_export`, `pdf`) et limites de fréquence (`ratelimit.py`) ;
  - fichiers (`files.py`) et format des dates (`dates.py`).
  - erreur de service (`core/errors.ServiceError`, base de toute erreur métier), réponses HTMX (`htmx.py` : `error_response`, `confirm_response`, `modal_form_response`, `form_error_response`, `location`), notifications à plusieurs personnes (`notify_many`, jamais une boucle de `notify`), filtres de liste (`components/filters.html`), texte saisi affiché sans HTML (filtre `plain_text`), contexte d'une action (`core/context.ActionContext`) : tout service qui agit prend `context: ActionContext` (vue : `ActionContext.of(request)` ; sans personne : `SYSTEM`), jamais la paire `actor`, `request`.
- Pour tout nouvel écran :
  - fin d'une action réussie : toujours `htmx.after_action` (R1-02) : même page, `refresh` (zone ou `PAGE_CHANGED`) ; autre page, `go_to` (HX-Location) ; formulaire de page complète, `page_form=True`. Jamais `messages` puis `redirect`, ni `HX-Location` ou `HX-Refresh` écrits à la main ;
  - filtres d'une liste : toujours `components/filters.html` avec un formulaire de filtres (options `classic`, `no_reset`, `form_id`, `extra_template`) ;
  - tout contrôle qui change l'affichage (vue, onglet, filtre, page) : un parcours Playwright en aller-retour, bouton Retour compris (`tests/e2e/test_round_trips.py`) ;
  - annulation immédiate : `undo.register(action, traitement, refresh=…)` et la vue commune `apps.core.views.undo_action` (URL avec le préfixe des actions) ; jamais une nouvelle vue d'annulation ;
  - contrainte de base : l'inscrire dans la table commune (`apps/core/constraints.register`) et traduire l'erreur par `constraints.translate`.
- Si une brique doit servir un deuxième usage, la faire évoluer au lieu d'en créer une variante.
- Annotations de type sur les fonctions de service et de sélection ; `make typecheck` (mypy, django-stubs) est bloquant sur tous les `services.py`, `selectors.py` et `apps/approvals/workflow/`.
- Moteur des demandes : paquet `apps/approvals/workflow/` (socle, valideurs, contrôles, notifications, transitions, annulation, campagnes). On l'importe toujours par la façade (`from apps.approvals import workflow`), et ses modules s'appellent entre eux par elle (`workflow._event(...)`) : un seul point d'entrée.
- Noms explicites en anglais.
- Docstring courte qui dit pourquoi, pas quoi.
- Pas de code mort, pas de TODO sans décision inscrite dans `docs/00-decisions.md`.
- Tests lisibles dont le nom dit le comportement vérifié (`test_employee_cannot_see_results`).

## Commandes

```bash
make up            # démarre PostgreSQL (Docker) et le serveur de développement
make css           # compile Tailwind en mode watch
make test          # pytest (unitaires et intégration)
make e2e           # tests de parcours Playwright
make lint          # ruff check, ruff format --check, djlint
make typecheck     # mypy sur les services et sélecteurs (bloquant)
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
