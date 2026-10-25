# Note de livraison : reprise technique refacto-1

Date : 25 octobre 2026. Branche : `refacto-1`, créée depuis `main` après la fusion du lot 6.

Reprise technique avant le lot 7, en deux temps, puis les corrections de la vérification.

- **Premier envoi** : aucun changement de comportement visible ; tous les tests passaient sans modification.
- **Second envoi** (décisions du 25 oct.) :
  - navigation unifiée (R1-02), le seul changement visible ;
  - `ActionContext` dans les services publics, avec un commit séparé qui adapte mécaniquement les appels des tests ;
  - filtres, contraintes et annulation par des briques uniques.

## Ce qui est fait

- **Erreurs de service.** Les huit classes d'erreur métier dérivent de `core.errors.ServiceError` : `WorkflowError`, `AdministrationError`, `PeopleError`, `ImportFileError`, `EquipmentError`, `InvitationError`, `UndoError` et `ExportDeniedError`. Leurs messages par défaut sont gardés. `StorageUnavailableError` reste à part : c'est une panne technique, pas un refus métier.
- **Notifications.** Les cinq boucles de `notify` passent par `notify_many`, qui renvoie maintenant les notifications créées : l'annulation immédiate d'une demande en a besoin. Ces boucles concernaient les valideurs d'une demande, la fermeture d'un site, le signalement de matériel, l'archivage d'un détenteur, la demande d'invitation et la démonstration.
- **Dates.** Plus aucun format écrit à la main.
  - Le journal exporté passe par `format_date` (styles `numeric` et `time`, nouveau).
  - Les formats techniques des noms de fichiers et de l'iCalendar sont nommés dans `dates.py` : `month_stamp`, `day_stamp`, `compact_day_stamp`, `ics_utc_stamp`. Le résultat est identique.
- **Réponses HTMX communes.**
  - Les 17 formulaires refusés rendus à la main passent par `form_error_response`, nouvelle brique réutilisée par `modal_form_response`.
  - Les 13 notifications d'erreur écrites en ligne passent par `error_response`.
  - Les 3 confirmations rendues directement passent par `confirm_response`, qui accepte maintenant `ok_icon`.
  - Les quatre rendus en 422 qui restent sont des pages complètes, pas des fragments : fiche de l'annuaire (2), paramètres de l'entreprise, réponse à un questionnaire.
- **Objet de contexte et arguments.** `core.context.ActionContext(actor, request)` remplace la paire `actor`, `request` dans les fonctions internes des services (`_record`, `_update_employee`, `_update_company`). Le seuil PLR0913 est **redescendu à 6**, et le projet le respecte :
  - `create_company` reçoit un objet `NewCompany` ;
  - la grille du planning reçoit un objet `GridPage` (page affichée, déclaration depuis la grille) ;
  - une case reçoit une date `declarable_from` au lieu du couple « peut déclarer », « aujourd'hui » ;
  - l'export du planning lit l'entreprise sur la personne ;
  - `log_export` perd deux paramètres que personne ne passait (code mort) ;
  - `confirm_response` reçoit ses options par mot-clé.
- **Moteur des demandes découpé.** `approvals/workflow.py` (931 lignes) devient le paquet `apps/approvals/workflow/` :

  | Module | Contenu | Lignes |
  |---|---|---|
  | `common` | erreurs, résultat d'une transition, verrous, événements, enregistrement contrôlé, fichier joint, agenda, journal | 238 |
  | `validators` | qui valide, qui peut décider ou annuler | 124 |
  | `checks` | contrôles métier (A3-02) | 150 |
  | `notifications` | valideurs et demandeur | 86 |
  | `transitions` | envoi, validation, refus, annulation | 263 |
  | `undo` | annulation immédiate | 138 |
  | `campaigns` | campagnes de congés d'été | 76 |

  Lignes après la vérification (annotations comprises).

  Les imports publics ne changent pas (`from apps.approvals import workflow`, `from apps.approvals.workflow import constraint_name`). Depuis la vérification, la façade n'exporte que les noms publics et les modules s'importent directement entre eux, sans cycle ; les deux tests qui remplaçaient `workflow._event` et `workflow._check_transport` injectent la panne plus bas (voir plus loin).
- **mypy et django-stubs** (R1-01) : mypy 2.4.0 et django-stubs 6.1.2, en dépendances de développement.
  - `make typecheck` est bloquant dans l'intégration continue sur les 11 `services.py` et `selectors.py` et sur le moteur des demandes (19 fichiers, 0 erreur).
  - Les 13 erreurs trouvées sont corrigées : annotations manquantes, `user` peut-être vide sur une fiche, type du résultat d'une transition.
  - Le reste du code sera vérifié au lot 8.
- **CLAUDE.md et architecture** : nouvelles briques, seuil de 6 arguments, règle de la façade `workflow`, commande `make typecheck`.

### Second envoi

- **Navigation unifiée (R1-02).** Une seule brique, `htmx.after_action`, termine toute action réussie (40 appels) :
  - même page : notification visuelle et rechargement de la zone ; `PAGE_CHANGED` recharge toute la zone `#content` ;
  - autre page : `HX-Location` ;
  - export : `HX-Redirect`, par la brique `download_response` depuis la vérification ;
  - seule exception : l'activation d'un module recharge le document entier (`refresh=RELOAD_PAGE`), car le menu change aussi.
  - La fiche de l'annuaire et les paramètres de l'entreprise passent par HTMX : erreurs en 422 sur place, plus de rechargement complet. Sans JavaScript (`page_form`), ces formulaires, l'import CSV et « Tout marquer comme lu » reçoivent un message, puis une redirection.
  - Une page rendue par un formulaire refusé se recharge depuis l'adresse affichée par le navigateur (`HX-Current-URL`), jamais depuis celle du POST. Un parcours l'avait révélé.
  - Les trois parcours annoncés passaient tels quels. Un seul parcours existant a changé, et de façon mécanique : `test_communication.py` prépare son questionnaire avec `context=ActionContext(…)` au lieu de `actor=…` (commit d'adaptation des appels). Deux nouveaux parcours vérifient que le document n'est pas rechargé (paramètres, création d'une fiche). Des tests unitaires couvrent `after_action` et l'adresse rechargée.
- **ActionContext dans les services publics.**
  - 36 fonctions de service prennent `context: ActionContext` au lieu de `actor` et `request` (`SYSTEM` pour une action sans personne : clôture automatique, plateforme). Les vues passent `ActionContext.of(request)`.
  - Trois actions exigent une personne (`context.person()`) : publier un questionnaire, publier une annonce, signaler un problème de matériel.
  - Commit séparé, mécanique : 30 appels de tests dans 9 fichiers passent de `actor=…` à `context=ActionContext(…)`, sans autre changement. Les 4 autres « actor= » comptés au départ créent des événements dans les fixtures, ce ne sont pas des appels de service.
- **Filtres.** Les six listes (annuaire, demandes, planning, parc du matériel, utilisateurs, journal) passent par `components/filters.html`, qui évolue :
  - sélecteur segmenté pour les boutons radio, champs cachés, `form_id`, zone de résultats ;
  - `classic=True` pour un envoi classique (le parc garde son bouton « Filtrer ») ;
  - `no_reset=True` ;
  - `extra_template` (choix liste ou cartes de l'annuaire, bouton « Inviter un utilisateur »).

  Trois nouveaux formulaires (`RequestFilterForm`, `PlanningFilterForm`, `ParkFilterForm`) reprennent exactement les noms, identifiants, libellés et choix. La disposition est vérifiée par captures.
- **Contraintes.** Une seule table, `apps/core/constraints.CONSTRAINT_MESSAGES` (champ, message), où chaque application inscrit ses contraintes (`register`, doublon refusé), avec `translate`. La façade `workflow` garde ses noms publics.
- **Annulation.** Une seule vue, `apps.core.views.undo_action`, et un registre `undo.register(action, traitement, refresh=…)`.
  - Les quatre URL existantes (demandes, matériel, annuaire, annonces) gardent leurs adresses et leurs noms ; elles passent à la vue le préfixe de leurs actions, et pour le matériel et les annonces le module et la permission, vérifiés avant le jeton comme avant.
  - Un jeton présenté à l'URL d'une autre application donne une page absente.
  - Une erreur de l'annulation d'un archivage, qui donnait une erreur 500, donne maintenant un refus (409).

### Avant la vérification (25 oct.)

- **Planning : second clic ignoré sur « Semaine » ou « Mois ».**
  - Le défaut existait aussi sur `main` : je l'ai reproduit avec le même parcours sur une copie de `main`. Il venait des barres de filtres du planning et de l'annuaire, avant la brique commune.
  - Cause : le déclencheur HTMX `input changed`. Le modificateur `changed` n'envoie la requête que si la valeur de l'élément qui émet l'événement a changé ; celle d'un bouton radio (« mois ») ne change jamais, et un second clic sur le même bouton était ignoré.
  - Correction dans la brique commune (`input delay:300ms`) : elle vaut pour tout sélecteur segmenté (planning, annuaire). Un champ texte n'émet « input » que si son texte change : le modificateur n'apportait rien.
  - Parcours ajoutés (`test_round_trips.py`) : Semaine, Mois, Semaine, Mois, puis deux retours ; Liste, Cartes, Liste, Cartes, puis deux retours. La vue affichée, le bouton coché et l'adresse sont vérifiés à chaque étape.
  - Autres contrôles testés en aller-retour, sans défaut : liste à choix d'un filtre, onglets, pagination, période précédente et suivante du planning.
- **Test du lien résiduel `xmin` rendu déterministe.** Il vérifie une relation toujours vraie : le `xmin` de chaque reçu est supérieur à celui de sa réponse et inférieur à celui de la réponse suivante. L'écart exact de 1 était faux dès qu'une autre transaction s'intercalait. Le test est passé six fois de suite avec une boucle parallèle d'environ 4 600 transactions par seconde. La documentation (L1-09, L6-03, fiches 03 et 09, `lot-6.md`) décrit la même relation.
- **Moteur des demandes et `ActionContext`.**
  - `submit`, `approve`, `refuse`, `cancel`, `cancel_approved`, `undo` et les trois fonctions des campagnes prennent `context: ActionContext`, comme les autres services. La personne n'est plus un argument positionnel, et `http_request` disparaît des signatures publiques.
  - Commit séparé, mécanique : 61 appels dans 8 fichiers de tests.

### Corrections de la vérification (25 oct.)

Chaque point a son test.

- **a. Cache des fragments.** Le middleware `HtmxCacheMiddleware` pose `Vary: HX-Request` sur toute réponse et `Cache-Control: no-store` sur celles d'HTMX. Sans lui, Retour puis Suivant après une action affichait le fragment seul (`<section class="card">` sans la page) : reproduit sur les fermetures et l'onglet « À valider » avant la correction. Tests unitaires des en-têtes ; parcours action, Retour, Suivant sur `/teletravail/`, l'onglet « À valider » et `/administration/fermetures/`.
- **b. Planning.** La date de l'adresse n'est plus ramenée au début de la période : Semaine, Mois, Semaine revient à la même semaine. Précédent et suivant partent du jour de référence (le mois suivant garde le même jour, borné à la fin du mois). Les liens `week_url` et `month_url`, inutilisés, sont retirés. Les parcours aller-retour passent par un gabarit commun, `round_trip` : chaque état est vérifié à l'aller, au Retour jusqu'au départ, puis au Suivant jusqu'au dernier ; la période du planning est vérifiée à chaque étape.
- **c. mypy.** `disallow_untyped_defs` et `disallow_incomplete_defs` dans le périmètre bloquant : 118 fonctions annotées (134 erreurs mypy, une fonction sans aucune annotation en donnant deux). `ignore_missing_imports` n'est plus global : seules allauth, botocore, django-environ et django-storages, sans types, sont nommées. Les annotations ont révélé quelques imprécisions, corrigées : `has_hr_step` devient un `TypeGuard[LeaveRequest]`, le champ du justificatif est vérifié avant l'écriture, la campagne verrouillée a son propre nom, le site d'une fermeture est testé explicitement. Test de la configuration.
- **d. Focus.** Après une action ou la fermeture d'une modale, le focus revient au bouton d'origine ; s'il a été remplacé par le rechargement de sa zone, à son remplaçant (même id ou même adresse d'action), sinon au premier élément utile de la zone (`ui.js`). La modale d'export se ferme après le téléchargement (`download_response`). Quatre parcours ; les deux premiers échouaient avant la correction.
- **e. Filtres.** `autocomplete="off"` sur tous les formulaires de filtres. L'annuaire redirige vers la même adresse avec la vue mémorisée quand `vue` manque ; « Réinitialiser » garde la vue. Parcours aller-retour du filtre « État » du parc.
- **f. Briques restantes.**
  - `storage_unavailable_response` sert aussi les requêtes HTMX (notification 503, la modale reste ouverte) ; l'envoi d'une demande l'utilise.
  - La consultation d'un justificatif est journalisée par le moteur (`workflow.record_proof_access`), plus par la vue.
  - `error_response` accepte `refresh` (erreur suivie du rechargement d'une zone, deux appels) et `go_to` ; l'import CSV l'utilise au lieu de `messages` puis `redirect`, et sa confirmation passe par HTMX.
  - `_audit`, `_campaign_audit`, `_undo_submit`, `_undo_decision`, `_submit`, `_approve_automatically` et `_create_employee` prennent `ActionContext` ; les reconstructions `ActionContext(actor, request)` des services de l'annuaire, de l'administration et du matériel disparaissent aussi.
- **g. Façade du moteur.** Les tests de la transaction d'envoi et de la traduction des contraintes injectent la panne sur `RequestEvent.objects.create` et par un enregistrement direct du modèle. Les modules s'importent directement ; la façade n'exporte que les noms publics ; `seed_demo` utilise `module_url`, devenu public.
- **h. CLAUDE.md.** Fin d'un export (`download_response`), erreur suivie d'un rechargement de zone (`error_response(refresh=…)`), `storage_unavailable_response`, middleware de cache, gabarit `round_trip`, annotations complètes.
- **i. Dates.** La note, R1-01 et R1-02 portaient le 26 oct., date à venir : corrigées au 25 oct. La même erreur dans le lot 6 (L6-19, L6-21, L6-23, `lot-6.md`) est corrigée aussi.

## Chiffres avant et après

| Mesure | Avant | Après |
|---|---|---|
| Classes d'erreur métier hors de `ServiceError` | 8 | 0 |
| Boucles de `notify` | 5 | 0 |
| Formats de date écrits à la main (`strftime`, `:%Y`…) | 11 | 0 |
| Fragments `#form` en 422 rendus à la main | 17 | 0 |
| Notifications d'erreur écrites en ligne | 13 | 0 |
| `confirm.html` rendu directement | 3 | 0 |
| Fonctions au-dessus de 10 de complexité | 0 | 0 |
| Fonctions au-dessus de 7 de complexité | 11 | 11 |
| Fonctions à plus de 6 arguments | 9 | 0 (seuil abaissé à 6) |
| Plus gros fichier du moteur des demandes | 931 lignes (`workflow.py`) | 263 lignes (`workflow/transitions.py`) |
| Erreurs mypy sur les services, sélecteurs et le moteur | 13 | 0 |
| Fonctions non annotées dans ce périmètre | 118 | 0 (`disallow_untyped_defs`) |
| `ignore_missing_imports` | global | 4 bibliothèques nommées |
| Réponses HTMX que le navigateur peut garder en cache | toutes | 0 (`no-store`, `Vary: HX-Request`) |
| `messages` puis `redirect` dans les vues | 3 (import CSV) | 0 |
| HX-Redirect écrit à la main | 1 | 0 (`download_response`) |
| Façons de naviguer après une action | 4 | 1 brique (`after_action`, 40 appels) |
| Paires `actor=request.employee, request=request` dans les vues | 27 | 0 (`ActionContext.of(request)`) |
| Barres de filtres écrites à la main | 6 | 0 |
| Tables `CONSTRAINT_MESSAGES` | 3 | 1 |
| Vues d'annulation | 4 | 1 |
| Exceptions `noqa` | 19 | 20 (une dans un test : classe imitant l'objet `diag` de psycopg) |

Plus gros fichiers (hors tests et migrations), après : `seed_demo.py` 1 072 lignes, `approvals/views.py` 617, `equipment/views.py` 510, `administration/views.py` 477, `people/views.py` 447, `equipment/services.py` 438.

## Ce qui reste pour le lot 8

- mypy sur tout le code (environ 100 erreurs, surtout des chaînes traduites paresseuses).
- Catalogue `locale/fr` (pluriels avec 0).
- Découpage de `seed_demo` (1 072 lignes) en un module par domaine.
- Les 11 fonctions entre 8 et 10 de complexité (`ui.control`, `_update_employee`, `count_today`…).

## Tests

| Commande | Résultat |
|---|---|
| `make lint` | sans erreur |
| `make typecheck` | 19 fichiers, aucune erreur (annotations complètes exigées) |
| `make test` | 798 tests : 796 réussis, 2 sautés (S3 sans MinIO local ; relance du transport, qui dépend du jour) ; couverture 96 % ; puis 6 tests de performance |
| `make e2e` | 64 parcours (2 pour la navigation, 10 pour les allers-retours, 4 pour le focus) ; un seul parcours existant modifié, mécaniquement (`test_communication.py`) |
| `make check` | aucune alerte |
