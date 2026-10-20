# Architecture

## Arborescence

```
dianna/
├── CLAUDE.md
├── Makefile
├── pyproject.toml              # dépendances (uv ou pip-tools), ruff, pytest
├── docker-compose.yml          # PostgreSQL 18 pour le développement
├── Dockerfile
├── .env.example
├── config/
│   ├── settings/{base,dev,test,prod}.py
│   ├── urls.py
│   └── wsgi.py / asgi.py
├── apps/
│   ├── core/          # Company, Site, Service, CompanyModule, TenantModel, middleware, permissions, audit, notifications, composants
│   ├── accounts/      # User, Invitation, connexion (allauth), profil de l'utilisateur
│   ├── people/        # Employee : annuaire, fiches, import CSV
│   ├── agenda/        # CalendarEvent, jours fériés, fermetures
│   ├── approvals/     # moteur commun des demandes + télétravail, congés, astreintes, transport
│   ├── equipment/     # parc, attributions, signalements, demandes de matériel
│   ├── planning/      # vues semaine et mois, exports
│   ├── announcements/ # communication interne
│   ├── surveys/       # questionnaires
│   ├── careers/       # entretiens, fiches de suivi
│   ├── interventions/ # comptes rendus d'intervention
│   ├── dashboard/     # tableau de bord
│   └── administration/# écrans de paramétrage de l'entreprise
├── templates/
│   ├── base.html, layouts/app.html, layouts/auth.html
│   ├── components/    # button, badge, field, table, pagination, modal, toast, empty_state, tabs, stepper…
│   └── <app>/ et <app>/partials/
├── static/
│   ├── css/app.css    # entrée Tailwind (jetons de reference/tokens.css)
│   ├── fonts/         # woff2 auto-hébergés
│   ├── js/            # ui.js (menus, modales, toasts, thème), htmx config
│   └── icons/sprite.svg  # icônes Lucide (licence ISC)
├── tests/e2e/         # Playwright
└── docs/
```

Les noms `agenda` et `approvals` évitent les conflits avec le module Python `calendar` et la bibliothèque `requests`.

## Multi-entreprise

Une base PostgreSQL, un schéma, une colonne `company_id` sur chaque table métier (décision T-07).

**Résolution de l'entreprise.** `CompanyMiddleware` lit le sous-domaine (`exemple.dianna.fr` → `Company.slug = "exemple"`), charge l'entreprise active et la place dans `request.company` et dans une `ContextVar` (`apps.core.tenancy.current_company`). Une entreprise suspendue renvoie une page dédiée. En développement, `exemple.localhost:8000` fonctionne, ou le paramètre `DEV_COMPANY_SLUG`.

**Hôtes (T-08, T-22).** `dianna.fr` : page vitrine (« Accéder à mon espace »). `admin.dianna.fr` : administration éditeur seule. `<slug>.dianna.fr` : espace d'une entreprise. Le domaine de base est le réglage `BASE_DOMAIN` (`dianna.fr`, `localhost` en développement).

**Modèle de base.**

```python
class TenantModel(models.Model):
    company = models.ForeignKey("core.Company", on_delete=models.CASCADE, editable=False)
    objects = TenantManager()        # filtre automatiquement sur current_company
    all_companies = models.Manager() # réservé aux commandes de plateforme, interdit dans les vues
    class Meta:
        abstract = True
```

- `TenantManager.get_queryset()` filtre sur `current_company` et **lie le queryset à cette entreprise**. À l'évaluation (lecture, comptage, mise à jour, suppression, sous-requête), il lève `NoCurrentCompanyError` sans entreprise courante et `CompanyMismatchError` si l'entreprise courante n'est pas celle de la construction, ou si le queryset a été construit sans entreprise (jamais de liste vide silencieuse ni de données d'une autre entreprise). En production, les vues et les formulaires sont importés pendant la première requête d'un processus : un queryset de classe serait lié à l'entreprise de cette requête.
- `save()` renseigne `company` depuis le contexte et refuse une incohérence.
- Les clés étrangères entre objets métier sont vérifiées par `clean()` (même entreprise).
- Les contraintes d'unicité incluent `company` (ex. `UniqueConstraint(fields=["company", "email"])`).
- Les tâches en arrière-plan reçoivent `company_id` en argument et ouvrent le contexte avec `with tenant_context(company):`.
- Le middleware remet la `ContextVar` à zéro dans un `finally` (`token = current_company.set(...)` puis `current_company.reset(token)`), pour qu'aucune requête n'hérite de l'entreprise d'une autre.
- **Interdit :** un queryset défini au niveau de la classe (`ModelChoiceField(queryset=X.objects.all())` dans le corps d'un formulaire) ; le poser dans `__init__`.
- L'administration Django de l'éditeur, les commandes (`seed_demo`) et les fabriques de test utilisent `all_companies` ou `tenant_context(company)`.
- Unicité : `company` étant `editable=False`, les ModelForm ne vérifient pas les contraintes qui l'incluent. Chaque formulaire vérifie explicitement l'unicité dans l'entreprise (`clean_email`, `clean_name`…) pour afficher le message prévu au lieu d'une `IntegrityError`.
- Règle des codes : objet existant mais hors du périmètre de l'utilisateur → **404** ; écran ou action interdits au profil → **403**.
- Lot 8 : Row Level Security PostgreSQL en défense en profondeur : `set_config('app.company_id', ..., true)` (portée transaction) avec `ATOMIC_REQUESTS`, jamais un `SET` de session (connexions persistantes) ; l'application se connecte avec un rôle **non propriétaire** des tables et les tables ont `FORCE ROW LEVEL SECURITY`.

**Tests d'isolation obligatoires.** Une fixture crée deux entreprises avec des données équivalentes. Pour chaque vue de liste, de détail, d'export et d'action : un utilisateur de l'entreprise A ne voit, ne modifie et n'exporte jamais une donnée de l'entreprise B (réponse 404, jamais 403, pour ne pas révéler l'existence de l'objet).

## Permissions

`apps/core/permissions.py` expose des fonctions pures, testées unitairement, qui suivent `04-permissions.md` :

```python
def can(user_employee, action: str, obj=None) -> bool: ...
# actions : "people.view_hr", "requests.decide", "careers.sign", "admin.manage_modules"…
def scope_queryset(user_employee, queryset, module: str) -> QuerySet: ...
# restreint à soi, à l'équipe ou à l'entreprise selon le profil
```

- Vues : mixin `PermissionRequiredMixin` maison (`permission = "requests.decide"`) et contrôle objet dans `get_object()`.
- Templates : balise `{% can "requests.decide" obj as ok %}` pour masquer les actions.
- Module désactivé : le décorateur `module_required("telework")` renvoie la page « Module désactivé ».
- Accès refusé : page 403 du design (« Accès non autorisé »), avec retour au tableau de bord.

## Circuit de validation commun

Toutes les demandes partagent la même machine à états (`apps/approvals/workflow.py`) :

```
(envoi)      → pending
pending      → approved | refused            (valideur)
pending      → manager_approved → approved | refused   (congés d'été avec étape RH)
pending      → cancelled                     (demandeur)
approved     → cancelled                     (RH ou administrateur, motif obligatoire ; L3-10)
```

**Annulation immédiate (« Annuler » dans la notification visuelle, 30 s côté serveur, auteur de l'action uniquement) :**
- après un envoi : la demande, son événement de calendrier et la notification au valideur sont **supprimés** ;
- après une décision (validation, refus, validation manager) : la demande revient à l'état précédent, un `RequestEvent` `reverted` est ajouté, la notification au demandeur est supprimée.

Les e-mails liés à une action annulable sont mis en file avec un **délai de 45 secondes** et ne partent pas si l'action a été annulée entre-temps.

Chaque transition est une fonction de service : vérifie l'état, enregistre un `RequestEvent` (qui, quand, quoi, commentaire), met à jour le `CalendarEvent` lié, crée les notifications, écrit le journal d'audit. Les transitions sont atomiques (`transaction.atomic`) et protégées contre la double soumission (`select_for_update`).

L'annulation immédiate proposée dans les notifications visuelles (bouton « Annuler ») appelle une transition inverse autorisée pendant 30 secondes après l'action, uniquement par son auteur (L0-03). Passé ce délai : notification d'erreur « Il est trop tard pour annuler cette action. ».

## Planning : événement de calendrier commun

`CalendarEvent(company, employee, kind, start, end, status, source_type, source_id)` est **créé dès l'envoi** de la demande (statut `pending`, affiché hachuré), passé en `approved` à la validation finale, et supprimé en cas de refus ou d'annulation. Il est alimenté par le télétravail, les congés et les astreintes (pas les interventions). Le planning ne lit **que** cette table. Statuts affichés : en attente (hachuré) et validé. Les jours sans événement sont « Sur site » les jours ouvrés, hors jours fériés et fermetures.

## HTMX : modèles d'interaction

| Interaction | Modèle |
|---|---|
| Recherche, filtres, tri, pagination | Formulaire `hx-get` sur la vue de liste, `hx-target="#results"`, `hx-push-url="true"`, `hx-trigger="input changed delay:300ms, submit"` (l'événement `input` couvre aussi les listes, les cases et les dates ; `change` en plus ajoutait une entrée d'historique en double). La vue renvoie le fragment `results` si `request.htmx`, la page entière sinon |
| Fenêtre modale | `hx-get` vers une vue qui renvoie le fragment de la modale dans `#modal-root`, élément `<dialog>` ouvert par `ui.js` |
| Envoi de formulaire | `hx-post` ; en cas d'erreur, la vue renvoie le formulaire avec les erreurs (statut 422 : HTMX 2 n'insère pas les réponses 4xx par défaut, configurer `htmx.config.responseHandling` dans `ui.js` pour insérer les 422) ; en cas de succès, en-tête `HX-Trigger` (`{"toast": {...}, "closeModal": true}`) et `HX-Redirect` ou nouveau rendu de la zone concernée |
| Notifications visuelles | Événement `toast` déclenché par l'en-tête `HX-Trigger`, ou messages Django rendus dans `#toasts` pour les pages complètes |
| Confirmation | Modale de confirmation commune (`components/confirm.html`), action en `hx-post` |
| Annuler (undo) | Lien dans la notification visuelle, `hx-post` vers l'URL d'annulation signée et limitée dans le temps |
| Lignes répétables (compte rendu d'intervention) | `hx-post` « ajouter une ligne » renvoyant un fragment de formulaire indexé ; suppression côté client et index recalculés à l'envoi |

Erreurs 5xx et réseau : événements `htmx:responseError` et `htmx:sendError` → bandeau « Le serveur n'a pas répondu. Vos saisies sont conservées, vous pouvez réessayer. » dans la modale ou le formulaire, sans perdre la saisie.

Le jeton CSRF est transmis globalement : `<body hx-headers='{"X-CSRFToken": "{{ csrf_token }}"}'>`. Sans JavaScript, les formulaires restent utilisables en envoi classique.

## Sécurité

- HTTPS partout, HSTS, cookies `Secure`, `HttpOnly`, `SameSite=Lax`.
- CSP stricte (intégrée à Django 6, `SECURE_CSP`) **dès le lot 0** : scripts et styles servis par l'application ; le script de thème en ligne porte `nonce="{{ csp_nonce }}"` ; `htmx.config.includeIndicatorStyles = false` (styles des indicateurs dans `app.css`) ; attributs `hx-on` interdits (ils exigent `unsafe-eval`).
- Fichiers déposés : analyse antivirus (ClamAV, à confirmer) avant de rendre le fichier accessible au valideur (lot 5).
- Double authentification pour RH et Administrateur. Limitation des tentatives de connexion.
- Mots de passe : validateurs Django, longueur minimale 12.
- Fichiers téléversés : types et tailles contrôlés côté serveur (PDF, JPG, PNG ; 5 Mo), noms aléatoires, bucket privé, URL signées après contrôle de permission.
- Journal d'audit (`AuditLog`) pour : connexion d'un administrateur, changement de profil, modification de fiche, décision sur une demande, export, accès support.
- Aucune donnée personnelle dans les journaux applicatifs ni dans Sentry (`send_default_pii=False`, filtrage).

## RGPD

- Hébergement et sauvegardes dans l'UE (France de préférence).
- Durées de conservation par type de donnée (M-13), appliquées par une tâche quotidienne.
- Export des données d'un salarié (droit d'accès) et d'une entreprise (réversibilité) : lot 8.
- Questionnaires : anonymat réel (M-10).
- Registre des traitements et modèle de contrat de sous-traitance (DPA) : documents juridiques hors code, à préparer avant commercialisation.

## Tests

| Type | Outil | Contenu minimal |
|---|---|---|
| Unitaires | pytest | Règles métier (`services.py`), permissions (`permissions.py`), validations de formulaires |
| Intégration | pytest-django, client de test | Chaque vue : accès par profil (200 / 403 / 404), isolation entre entreprises, réponses HTMX |
| Bout en bout | Playwright | Les parcours de `08-prompts-claude-code.md`, repris du prototype |
| Accessibilité | axe-core via Playwright | Pages principales sans violation critique |

## Déploiement

- Image Docker unique (Gunicorn, WhiteNoise pour les fichiers statiques), travailleur de tâches séparé utilisant la même image : `python manage.py db_worker` (django-tasks-db, L3-01), et purge quotidienne `prune_db_task_results`.
- E-mails : toujours par une tâche (`apps/core/mail.py`) ; ceux d'une action annulable partent après 45 s et seulement si la notification existe encore.
- Environnements : développement local, recette, production.
- Migrations lancées au déploiement. Sauvegarde PostgreSQL quotidienne avec test de restauration mensuel.
- Intégration continue : lint, tests, construction de l'image, à chaque demande de fusion.
