# Note de livraison : reprise technique refacto-1

Date : 26 octobre 2026. Branche : `refacto-1`, créée depuis `main` après la fusion du lot 6.

Reprise technique avant le lot 7. Il n'y a aucun changement de comportement visible : tous les tests existants passent sans modification (unitaires, intégration, performance, parcours). La navigation unifiée n'est pas appliquée, car elle changerait le comportement ; elle est proposée plus bas et attend ton accord.

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
| Exceptions `noqa` | 19 | 19 |

Plus gros fichiers (hors tests et migrations), après : `seed_demo.py` 1 071 lignes, `approvals/views.py` 644, `equipment/views.py` 517, `administration/views.py` 483, `people/views.py` 447, `core/models.py` 426.

## Ce qui reste

- **Navigation après une action** : proposition ci-dessous, à valider.
- **Appels des vues** : les 27 appels `actor=request.employee, request=request` restent. Les services publics gardent leurs arguments nommés, car 34 appels dans 10 fichiers de tests les utilisent ainsi. Passer l'`ActionContext` aux services publics demanderait de modifier ces tests : à faire avec ton accord, par exemple au début du lot 7.
- **Filtres de liste** : six listes des lots 1 à 5 écrivent encore leur formulaire de filtres au lieu de `components/filters.html` (hors du périmètre demandé ; écart de mise en page à vérifier écran par écran).
- **Traduction des contraintes** : `CONSTRAINT_MESSAGES` existe encore trois fois (demandes, matériel, annuaire).
- **Annulation immédiate** : quatre vues lisent encore le jeton de la même façon.
- **Lot 8** :
  - mypy sur tout le code (environ 100 erreurs, surtout des chaînes traduites paresseuses) ;
  - catalogue `locale/fr` ;
  - découpage de `seed_demo` ;
  - fonctions entre 8 et 10 de complexité (`ui.control`, `_update_employee`, `count_today`…).

## Proposition : une seule façon de naviguer après une action

**Aujourd'hui, quatre façons coexistent :**

| Situation | Façon | Où |
|---|---|---|
| Formulaire en page complète | message, puis redirection classique (rechargement complet) | fiche de l'annuaire (création, modification), paramètres de l'entreprise, import CSV, « Tout marquer comme lu » |
| Action dans une modale, le résultat est sur la page | notification visuelle, puis événement HTMX qui recharge la zone concernée | matériel, demandes, archivage, structure, fermetures, profils |
| Action dans une modale, le résultat est une autre page | notification visuelle, puis `HX-Location` (seule la zone `#content` change) | annonces, questionnaires |
| Export | `HX-Redirect` vers le fichier | exports des demandes |

**Proposition.** Une seule brique, `after_action(request, toast, *, refresh=None, go_to=None)`, et une seule règle :

1. Le résultat reste sur la page : notification visuelle et rechargement de la zone (`refresh`). C'est le cas actuel des modales.
2. Le résultat est une autre page : notification visuelle et `HX-Location` vers cette page (`go_to`).
   - Les formulaires en page complète passent par HTMX, avec erreurs en 422 sur place, et ne rechargent plus tout le document.
   - Les annonces épinglées ou modifiées restent sur leur page et rechargent seulement la zone (règle 1).
3. L'export n'est pas une navigation : il garde `HX-Redirect` vers le fichier.

**Ce qui change à l'écran.**
- Après la création ou la modification d'une fiche et l'enregistrement des paramètres, la page ne se recharge plus entièrement. Le message devient une notification visuelle, identique à celle des modales, et l'adresse change comme aujourd'hui.
- Après « Épingler » ou « Modifier » une annonce, la page n'est plus rechargée par `HX-Location` mais dans sa zone.
- Sans JavaScript, les formulaires gardent leur envoi classique.

**Parcours touchés** : `test_people_admin` (création et modification d'une fiche), `test_socle` (paramètres) et `test_communication` (épinglage). Leurs attentes de navigation seront adaptées, rien d'autre.

## Tests

| Commande | Résultat |
|---|---|
| `make lint` | sans erreur |
| `make typecheck` | 19 fichiers, aucune erreur |
| `make test` | 774 tests : 772 réussis, 2 sautés (S3 sans MinIO local ; relance du transport, qui dépend du jour) ; puis 6 tests de performance |
| `make e2e` | 48 parcours, sans modification |
| `make check` | aucune alerte |
