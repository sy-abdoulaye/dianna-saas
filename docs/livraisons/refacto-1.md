# Note de livraison : reprise technique refacto-1

Date : 26 octobre 2026. Branche : `refacto-1`, créée depuis `main` après la fusion du lot 6.

Reprise technique avant le lot 7, en deux temps.

- **Premier envoi** : aucun changement de comportement visible ; tous les tests passaient sans modification.
- **Second envoi** (décisions du 26 oct.) :
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
  | `common` | erreurs, résultat d'une transition, verrous, événements, enregistrement contrôlé, fichier joint, agenda, journal | 218 |
  | `validators` | qui valide, qui peut décider ou annuler | 122 |
  | `checks` | contrôles métier (A3-02) | 148 |
  | `notifications` | valideurs et demandeur | 75 |
  | `transitions` | envoi, validation, refus, annulation | 253 |
  | `undo` | annulation immédiate | 123 |
  | `campaigns` | campagnes de congés d'été | 72 |

  Les imports publics ne changent pas (`from apps.approvals import workflow`, `from apps.approvals.workflow import constraint_name`). Les modules s'appellent entre eux par la façade `workflow` : un seul point d'entrée, et les deux tests qui remplacent `workflow._event` et `workflow._check_transport` gardent tout leur sens sans être modifiés.
- **mypy et django-stubs** (R1-01) : mypy 2.4.0 et django-stubs 6.1.2, en dépendances de développement.
  - `make typecheck` est bloquant dans l'intégration continue sur les 11 `services.py` et `selectors.py` et sur le moteur des demandes (19 fichiers, 0 erreur).
  - Les 13 erreurs trouvées sont corrigées : annotations manquantes, `user` peut-être vide sur une fiche, type du résultat d'une transition.
  - Le reste du code sera vérifié au lot 8.
- **CLAUDE.md et architecture** : nouvelles briques, seuil de 6 arguments, règle de la façade `workflow`, commande `make typecheck`.

### Second envoi

- **Navigation unifiée (R1-02).** Une seule brique, `htmx.after_action`, termine toute action réussie (40 appels) :
  - même page : notification visuelle et rechargement de la zone ; `PAGE_CHANGED` recharge toute la zone `#content` ;
  - autre page : `HX-Location` ;
  - export : `HX-Redirect`, inchangé ;
  - seule exception : l'activation d'un module recharge le document entier (`refresh=RELOAD_PAGE`), car le menu change aussi.
  - La fiche de l'annuaire et les paramètres de l'entreprise passent par HTMX : erreurs en 422 sur place, plus de rechargement complet. Sans JavaScript (`page_form`), ces formulaires, l'import CSV et « Tout marquer comme lu » reçoivent un message, puis une redirection.
  - Une page rendue par un formulaire refusé se recharge depuis l'adresse affichée par le navigateur (`HX-Current-URL`), jamais depuis celle du POST. Un parcours l'avait révélé.
  - Les trois parcours annoncés passaient tels quels : aucun parcours existant n'a été modifié. Deux nouveaux parcours vérifient que le document n'est pas rechargé (paramètres, création d'une fiche). Des tests unitaires couvrent `after_action` et l'adresse rechargée.
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
| Plus gros fichier du moteur des demandes | 931 lignes (`workflow.py`) | 253 lignes (`workflow/transitions.py`) |
| Erreurs mypy sur les services, sélecteurs et le moteur | 13 | 0 |
| Façons de naviguer après une action | 4 | 1 brique (`after_action`, 40 appels) |
| Paires `actor=request.employee, request=request` dans les vues | 27 | 0 (`ActionContext.of(request)`) |
| Barres de filtres écrites à la main | 6 | 0 |
| Tables `CONSTRAINT_MESSAGES` | 3 | 1 |
| Vues d'annulation | 4 | 1 |
| Exceptions `noqa` | 19 | 20 (une dans un test : classe imitant l'objet `diag` de psycopg) |

Plus gros fichiers (hors tests et migrations), après : `seed_demo.py` 1 072 lignes, `approvals/views.py` 627, `equipment/views.py` 510, `administration/views.py` 478, `people/views.py` 435, `core/models.py` 426.

## Ce qui reste pour le lot 8

- mypy sur tout le code (environ 100 erreurs, surtout des chaînes traduites paresseuses).
- Catalogue `locale/fr` (pluriels avec 0).
- Découpage de `seed_demo` (1 072 lignes) en un module par domaine.
- Les 11 fonctions entre 8 et 10 de complexité (`ui.control`, `_update_employee`, `count_today`…).
- Le moteur des demandes (`workflow.approve`, `refuse`…) garde sa convention propre : la personne en argument positionnel et `http_request`, que 61 appels de tests utilisent. Il peut passer à `ActionContext` de la même façon, avec ton accord pour ces tests.

## Tests

| Commande | Résultat |
|---|---|
| `make lint` | sans erreur |
| `make typecheck` | 19 fichiers, aucune erreur |
| `make test` | 784 tests : 782 réussis, 2 sautés (S3 sans MinIO local ; relance du transport, qui dépend du jour) ; puis 6 tests de performance |
| `make e2e` | 50 parcours (2 nouveaux pour la navigation) ; aucun parcours existant modifié |
| `make check` | aucune alerte |
