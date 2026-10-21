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
pending, manager_approved → cancelled        (demandeur, tant que la décision finale n'est pas prise)
approved     → cancelled                     (RH ou administrateur, motif obligatoire ; L3-10)
```

**Annulation immédiate (« Annuler » dans la notification visuelle, 30 s côté serveur, auteur de l'action uniquement) :**
- après un envoi : la demande, son événement de calendrier, ses notifications et son historique (`RequestEvent`) sont **supprimés** ; le journal d'audit garde la trace « Demande envoyée puis retirée » (L1-08) ;
- après une décision (validation, refus, validation manager, annulation) : la demande revient à l'état précédent (après une validation finale RH d'un congé d'été : « Validée par le manager »), un `RequestEvent` `reverted` est ajouté ;
- toutes les notifications de la demande dont l'e-mail n'est pas encore parti sont retirées ; si la demande est de nouveau en attente, les valideurs actuels reçoivent une nouvelle notification « à valider » (A3-05) ;
- le jeton porte l'identifiant du `RequestEvent` créé par la transition : l'annulation n'est acceptée, sous verrou de la demande, que si cet événement est toujours le dernier. Sinon : « Une autre décision a été prise depuis. Rien n'a été modifié. » (409, A3-01) ;
- si la demande redevient active (refus ou annulation défaits), les contrôles métier sont refaits sous le même verrou que l'envoi ; s'ils échouent, l'annulation est refusée avec le message habituel (A3-02).

**Contrôles métier (A3-02) :** quota de télétravail, une demande par jour, chevauchement des congés et des astreintes, période de la campagne sont faits par `check_request` dans `workflow.py`, sous verrou de la fiche du demandeur (ordre des verrous : fiche, puis demande). Les formulaires ne vérifient que leurs champs ; la vue appelle le service et affiche ses erreurs (`RequestValidationError`). Une violation de contrainte en base devient un message, jamais une erreur 500.

Les e-mails liés à une action annulable sont mis en file avec un **délai de 45 secondes** et ne partent pas si l'action a été annulée entre-temps.

Chaque transition est une fonction de service : vérifie l'état, enregistre un `RequestEvent` (qui, quand, quoi, commentaire), met à jour le `CalendarEvent` lié, supprime les notifications de la demande devenues fausses dont l'e-mail n'est pas parti (A3-05), crée les nouvelles, écrit le journal d'audit. Les transitions sont atomiques (`transaction.atomic`) et protégées contre la double soumission (`select_for_update`).

L'annulation immédiate proposée dans les notifications visuelles (bouton « Annuler ») appelle une transition inverse autorisée pendant 30 secondes après l'action, uniquement par son auteur (L0-03). Passé ce délai : notification d'erreur « Il est trop tard pour annuler cette action. ».

## Planning : événement de calendrier commun

`CalendarEvent(company, employee, kind, start, end, status, source_type, source_id)` est **créé dès l'envoi** de la demande (statut `pending`, affiché hachuré), passé en `approved` à la validation finale, et supprimé en cas de refus ou d'annulation. Il est alimenté par le télétravail, les congés et les astreintes (pas les interventions). Le planning ne lit **que** cette table. Statuts affichés : en attente (hachuré) et validé. Les jours sans événement sont « Sur site » les jours ouvrés, hors jours fériés et fermetures.

**Jours non ouvrés (T-16).** `apps/agenda/days.py` : jours fériés du paquet `holidays` (France, Alsace-Moselle pour les sites qui ont ce réglage, L4-02) et fermetures `Closure` saisies par l'administrateur (entreprise ou site). `DayOffs(début, fin)` charge une période en deux requêtes. Le télétravail est refusé ces jours-là par `check_request` (envoi et annulation immédiate) ; congés et astreintes ne sont pas concernés.

**Calcul de la grille (`apps/planning/services.py`).** Case : « — » avant l'arrivée, vide le week-end, libellé du jour férié ou de la fermeture, puis congés > télétravail > sur site ; repère « A » de l'astreinte cumulé (L1-07, L4-01). Requêtes par grille, quel que soit l'effectif : les personnes de la page, leurs événements de la période, les fermetures, les sites d'Alsace-Moselle, la répartition du jour. 50 personnes par page, la personne connectée en tête (L4-07). Mesuré pour 200 personnes sur un mois : vue mois 160 à 200 ms, export CSV environ 70 ms, export Excel 145 à 180 ms (test `apps/planning/tests/test_performance.py`, budget 300 ms).

## Exports

| Format | Module | Règles |
|---|---|---|
| CSV | `apps/core/csv_export.py` | point-virgule, UTF-8 avec BOM, cellules neutralisées (=, +, -, @, tabulation, retour chariot préfixés d'une apostrophe) |
| Excel | `apps/core/xlsx_export.py` (openpyxl, écriture seule) | même neutralisation, toute cellule texte enregistrée comme texte ; couleurs lues dans les jetons de `app.css` (`apps/core/tokens.py`) |
| iCalendar | `apps/core/ics_export.py` | sans dépendance : échappement et lignes de 75 octets (RFC 5545) ; fichier téléchargé, abonnement au lot 8 |
| PDF | `apps/core/pdf.py` (WeasyPrint) | gabarit HTML, A4 paysage ; récupérateur d'URL fermé (`DiannaURLFetcher`) : seuls `https://dianna.invalid/static/css|fonts/…` et le logo de l'entreprise courante ; toute autre adresse refusée sans requête (L4-06) |

Chaque export vérifie le périmètre côté serveur avec la même fonction que la vue et s'inscrit au journal d'audit avec la période, le format et le périmètre, sans nom de personne (L4-12). Les cases suivent la règle de confidentialité du planning (L4-16, `services.sees_details`).

**Limites de fréquence (L1-16, L4-17).** Toute limite de fréquence passe par `apps/core/ratelimit.py`, jamais par le cache : un cache local ou borné peut perdre un compteur quand d'autres clés arrivent et n'est pas partagé entre processus. Compteur `RateLimitCounter` (empreinte HMAC de la clé, début de fenêtre fixe, nombre ; contrainte unique), incrémenté en une seule requête PostgreSQL : `INSERT … ON CONFLICT (key, window_start) DO UPDATE SET count = count + 1 RETURNING count`. Deux requêtes simultanées ne lisent jamais le même nombre (test : 30 exports simultanés, 10 acceptés). Fenêtres expirées supprimées par `purge_task_results`. Utilisé par la vitrine (10 essais par adresse IP, 3 par adresse saisie, par 10 minutes) et les exports (10 par personne et par 10 minutes). Les limites internes d'allauth (connexion, mot de passe oublié) utilisent encore le cache partagé en base.

**Coût des exports (L4-17).** Les exports sont générés pendant la requête : le PDF est limité à 50 personnes et un mois (environ 2 s ; mémoire résidente d'un processus qui ne fait que ce rendu : 92 Mo avant, 146 Mo au maximum, mesurée avec le module resource), et chaque personne a droit à `EXPORT_LIMIT` = 10 exports par `EXPORT_PERIOD` = 10 minutes (`apps/core/ratelimit.py`, compteur en base). Gunicorn arrête une requête au-delà de 30 s (`--timeout 30` dans le Dockerfile). La génération en arrière-plan des gros exports est prévue au lot 8 si un client en a besoin.

## Fichiers privés (T-12, L5-01, L5-02)

- `apps/core/files.py` : un seul stockage privé, choisi par `PRIVATE_STORAGE_BACKEND` : disque (`PRIVATE_MEDIA_ROOT`, développement et tests) ou S3 (`django-storages`, Scaleway Object Storage fr-par en production, MinIO dans l'intégration continue ; bucket privé par environnement, `default_acl=private`, chiffrement côté serveur `S3_SERVER_SIDE_ENCRYPTION`). `manage.py check --deploy` vérifie la configuration S3 (`dianna.E009`, `dianna.W009`, `dianna.W010`).
- Chemins : `<company_id>/photos/`, `<company_id>/logo/`, `<company_id>/transport/` suivis d'un nom aléatoire ; le nom d'origine n'est jamais utilisé pour le stockage (conservé pour l'affichage et `Content-Disposition`).
- Contrôle (`clean_document`) : lecture par morceaux arrêtée au-delà de 5 Mo ; type reconnu sur le contenu (signature PDF et fin de fichier, ou image relue par Pillow et réencodée sans métadonnées) ; PDF chiffrés refusés.
- Service (`serve_isolated`) : `FileResponse` avec le type exact, `nosniff`, `Content-Security-Policy: sandbox; default-src 'none'; img-src 'self'`, `Cache-Control: private, no-store`, `Cross-Origin-Resource-Policy: same-origin`, nom échappé (RFC 6266). La vue `approvals:proof_file` vérifie `transport.view` et journalise toute consultation par une autre personne que le demandeur. La vue des liens signés (`core:private_file`) refuse tout chemin hors photos et logos.
- Les fichiers ne suivent pas les transactions : `workflow.submit` supprime le fichier si l'envoi échoue après son écriture ; l'annulation immédiate d'un envoi le supprime après validation de la transaction.

## Matériel (`apps/equipment`)

Services sous verrou de l'équipement (`select_for_update`), historique `EquipmentEvent`, notifications, journal. Un seul détenteur garanti en base (L5-08). Les demandes de matériel sont un type du moteur commun (`EquipmentRequest`, `register_request_model`, `register_kind`) : valider, refuser, annuler et l'historique sont ceux du moteur ; l'écran `/materiel/` est celui de l'application (inclus avant les routes des demandes). Types « validés par les RH » (`hr_validated`) : transport et matériel, avec leurs propres actions de permission (`create_action`, `view_action`, `decide_action`).

## Tâches quotidiennes

`manage.py enqueue_daily_tasks` met en file, pour chaque entreprise active, la relance des abonnements annuels de transport (L5-12), exécutée par le travailleur. Le service `scheduler` du profil `taches` l'enchaîne avec `purge_task_results` une fois par jour ; en production, au lot 8.

## HTMX : modèles d'interaction

| Interaction | Modèle |
|---|---|
| Recherche, filtres, tri, pagination | Formulaire `hx-get` sur la vue de liste, `hx-target="#results"`, `hx-push-url="true"`, `hx-trigger="input changed delay:300ms, submit"` (l'événement `input` couvre aussi les listes, les cases et les dates ; `change` en plus ajoutait une entrée d'historique en double). La vue renvoie le fragment `results` si `request.htmx`, la page entière sinon |
| Fenêtre modale | `hx-get` vers une vue qui renvoie le fragment de la modale dans `#modal-root`, élément `<dialog>` ouvert par `ui.js` |
| Envoi de formulaire | `hx-post` ; en cas d'erreur, la vue renvoie le formulaire avec les erreurs (statut 422 : HTMX 2 n'insère pas les réponses 4xx par défaut, configurer `htmx.config.responseHandling` dans `ui.js` pour insérer les 422) ; en cas de succès, en-tête `HX-Trigger` (`{"toast": {...}, "closeModal": true}`) et `HX-Redirect` ou nouveau rendu de la zone concernée |
| Notifications visuelles | Événement `toast` déclenché par l'en-tête `HX-Trigger` (JSON en ASCII, L5-16), ou messages Django rendus dans `#toasts` pour les pages complètes |
| Confirmation | Modale de confirmation commune (`components/confirm.html`), action en `hx-post` |
| Annuler (undo) | Lien dans la notification visuelle, `hx-post` vers l'URL d'annulation signée et limitée dans le temps |
| Lignes répétables (compte rendu d'intervention) | `hx-post` « ajouter une ligne » renvoyant un fragment de formulaire indexé ; suppression côté client et index recalculés à l'envoi |

Erreurs 5xx et réseau : événements `htmx:responseError` et `htmx:sendError` → bandeau « Le serveur n'a pas répondu. Vos saisies sont conservées, vous pouvez réessayer. » dans la modale ou le formulaire, sans perdre la saisie.

Le jeton CSRF est transmis globalement : `<body hx-headers='{"X-CSRFToken": "{{ csrf_token }}"}'>`. Sans JavaScript, les formulaires restent utilisables en envoi classique.

## Sécurité

- HTTPS partout, HSTS, cookies `Secure`, `HttpOnly`, `SameSite=Lax`.
- CSP stricte (intégrée à Django 6, `SECURE_CSP`) **dès le lot 0** : scripts et styles servis par l'application ; le script de thème en ligne porte `nonce="{{ csp_nonce }}"` ; `htmx.config.includeIndicatorStyles = false` (styles des indicateurs dans `app.css`) ; attributs `hx-on` interdits (ils exigent `unsafe-eval`).
- Fichiers déposés : pas d'analyse antivirus au lot 5 (ni service ClamAV ni dépendance) ; les justificatifs ne sont jamais exécutés ni affichés comme une page (service isolé, L5-01). Décision à prendre au lot 8 (« Pour plus tard »).
- Double authentification pour RH et Administrateur. Limitation des tentatives de connexion.
- Mots de passe : validateurs Django, longueur minimale 12.
- Fichiers téléversés : type réel et taille contrôlés côté serveur (PDF, JPG, PNG ; 5 Mo, lus par morceaux), images réencodées sans métadonnées, PDF chiffrés refusés (L5-03), noms aléatoires rangés par entreprise, bucket privé. Photos et logos : URL signées de 5 minutes (A2-07). Justificatifs : jamais de lien signé, servis par une vue qui vérifie la permission à chaque téléchargement, avec `nosniff`, `sandbox` et le type exact (L5-01).
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

- Image Docker unique (Gunicorn, WhiteNoise pour les fichiers statiques), travailleur de tâches séparé utilisant la même image : `python manage.py db_worker` (django-tasks-db, L3-01), et purge quotidienne `purge_task_results`. L'image contient Pango et HarfBuzz pour les exports PDF (WeasyPrint) ; `XDG_CACHE_HOME=/tmp` pour le cache de Fontconfig. Gunicorn : 3 processus, `--timeout 30` (une requête plus longue arrête son processus), `--graceful-timeout 30`.
- Profil `taches` de `docker-compose.yml` (services `migrate`, `worker` et `scheduler`) : **développement et essais seulement**, avec `config.settings.dev` et la base `db` du fichier (`DATABASE_URL` forcée sur `db:5432`, le `.env` de la machine n'est pas modifié). Le déploiement en production du travailleur et de la purge est fait au **lot 8**.
- E-mails : toujours par une tâche (`apps/core/mail.py`, `apps/core/tasks.py`) ; ceux d'une action annulable partent après 45 s et seulement si la notification existe encore. Une transition supprime les notifications de la demande dont l'e-mail n'est pas parti et qui ne sont plus vraies (A3-05).
- Les tâches d'e-mail de Dianna reçoivent `company_id` et n'envoient rien si l'entreprise est suspendue. `send_encrypted_email` (e-mails d'allauth) n'a pas d'entreprise : son contenu, déjà rendu, est chiffré.
- Aucune donnée sensible en clair dans une ligne de tâche (A3-04) :
  - les e-mails de Dianna (notification, invitation, lien de l'espace) passent des identifiants ; le texte et les liens sont construits au moment de l'envoi ;
  - le jeton d'invitation est créé dans la tâche : il n'existe en clair que dans l'e-mail ; son empreinte n'est enregistrée qu'une fois l'e-mail accepté par le serveur d'envoi. En cas d'échec, l'invitation précédente reste valable et la nouvelle est marquée « Envoi échoué » ;
  - les e-mails d'allauth, déjà rendus (mot de passe oublié…), sont chiffrés avec `TASKS_ENCRYPTION_KEY` (`MultiFernet`, comme `MFA_ENCRYPTION_KEY`, clé distincte, obligatoire en production) ;
  - le résultat d'une tâche réussie est supprimé dès sa fin (signal `task_finished`) ; les échecs sont purgés après 7 jours.
- Environnements : développement local, recette, production.
- Migrations lancées au déploiement. Sauvegarde PostgreSQL quotidienne avec test de restauration mensuel.
- Intégration continue : lint, tests, construction de l'image, à chaque demande de fusion.
