# Note de livraison : lot 6, communication interne et questionnaires

Date : 24 octobre 2026. Branche : `lot-6`.

## Étape 0 : qualité du code (commit séparé)

- **ruff.** Nouvelles règles : C90 (complexité ≤ 10), RET, PTH, PLR0911 à PLR0915 (6 `return`, 12 branches, 8 arguments, 50 instructions). B, SIM, DJ et N étaient déjà actives.
- **Seuil d'arguments.** Il est de 8, et non 6 : les services prennent des arguments nommés (`*, actor, request`), que PLR0913 compte aussi.
- **Code existant corrigé**, sans changement de comportement (tests inchangés) :
  - `request_list` : lectures déplacées dans le nouveau `apps/approvals/selectors.py` ;
  - `export_requests` : table des exports ;
  - `check_request` : une fonction par type de demande ;
  - `undo` : verrou, retrait d'un envoi, retour sur une décision ;
  - `indicators` du tableau de bord : une fonction par profil ;
  - `check` de l'import CSV : champs, e-mail, manager ;
  - formulaire d'export du planning : périodes prédéfinies ;
  - `grid` du planning : objet `PeopleFilter` ;
  - `button` : classes et attributs ;
  - `seed_demo` : classe `DemoRequestWriter`, une méthode par module ;
  - `pdf.py` : `Path.read_bytes`.
- **Exceptions `noqa`.** Il y en a 21 dans le projet (14 dans le code et les réglages, 7 dans les tests), chacune avec sa raison sur la ligne (audit du 25 oct.). Deux sont nées pendant ce lot :
  - `apps/core/templatetags/ui.py`, `button` : `PLR0913`, un argument par attribut HTML, API utilisée par tous les gabarits ;
  - `apps/core/templatetags/ui.py`, `plain_text` : `S308`, `mark_safe` sur un texte déjà échappé par `urlize`.
- **CLAUDE.md.** Nouvelle section « Qualité du code ».

## Ce qui est fait

**Communication interne (fiche 08).**
- Liste :
  - « N annonces non lues » ou « Vous avez tout lu » ;
  - recherche et filtre de catégorie (composant commun des filtres) ;
  - point « non lue », épinglées en premier puis par date, extrait de 140 caractères, pagination.
- Lecture : la première ouverture marque l'annonce comme lue, pour cette seule personne. Une contrainte unique garantit une seule lecture, même pour deux ouvertures simultanées.
- Texte : il est échappé, les liens `http`, `https` et e-mail sont détectés (`rel="nofollow"`), les retours à la ligne sont gardés. `<script>` s'affiche comme du texte (filtre `plain_text`).
- Gestion, réservée aux RH et à l'administrateur :
  - publier, modifier, épingler ou désépingler ;
  - supprimer, avec confirmation, puis « Annuler » pendant 30 s (suppression logique, L6-09) ;
  - le lien d'une ancienne notification affiche « Cette annonce a été supprimée. ».
- Publication : une notification à chaque personne présente, en une seule insertion (`notify_many`). L'e-mail ne part que pour une annonce épinglée (L6-08).
- Lectures « x sur y » : visibles seulement de l'auteur, des RH et de l'administrateur (L6-14).
- Journal : une ligne par action, sans le contenu.
- Tableau de bord : indicateur « Annonces non lues » pour le salarié, bloc « Annonces » (3 dernières, « Nouveau »).

**Questionnaires (fiche 09).**
- **Anonymat réel.**
  - Les réponses (`SurveyResponse`, `Answer`) héritent de `TenantBase`, la nouvelle base sans horodatage (L6-12).
  - Elles ont une clé UUID4 aléatoire, aucune date (`submitted_on` supprimé, L6-02) et aucun lien vers la personne ou le reçu.
  - Le reçu et la réponse sont créés dans la même transaction : la réponse dans la transaction du service, le reçu dans une sous-transaction. Le `xmin` du reçu vaut donc celui de la réponse + 1, ce qui est un lien résiduel en base (L1-09).
  - Répondre n'écrit ni journal, ni notification, ni tâche.
- **Public figé à la publication** (L6-04). Un public de moins de 5 personnes ne peut pas être publié (L6-05, L6-17).
- **Seuil d'anonymat appliqué partout.**
  - Une seule règle, `results_visible`, par laquelle passe `survey_results`.
  - Résultats visibles après la clôture ou l'échéance passée, à partir de 5 réponses (L6-01, L6-17).
  - Avant : le nombre de réponses seulement, jamais de noms.
  - Commentaires triés par note décroissante ; à note égale, l'ordre suit la clé aléatoire.
- **Réponse.**
  - Note de 1 à 5 obligatoire, commentaire facultatif, question ouverte facultative.
  - Une seule réponse : une contrainte unique sur le reçu refuse un formulaire renvoyé.
  - Refus après l'échéance ou hors du public.
- **Cycle de vie.**
  - Brouillon : créer, « Modifier le brouillon » (L6-07, écart au prototype), supprimer.
  - Publier, avec confirmation et notification au public.
  - Clore, avec confirmation. La clôture est aussi automatique le lendemain de l'échéance, par `enqueue_daily_tasks` (L6-06).
- **Écrans.**
  - Liste avec le bandeau « N questionnaires à remplir ».
  - Page avec, selon le cas, « Répondre / Résultats », l'aperçu du brouillon, ou « Merci » et « Clos ».
  - Les brouillons sont en 403 hors RH et administrateur. Un salarié ne voit pas un questionnaire qui ne lui est pas destiné (404).

**Briques communes, que j'ai fait évoluer au lieu d'en créer des variantes (L6-13)** :
- `notify_many` ;
- `htmx.location` ;
- `htmx.error_response`, `confirm_response`, `modal_form_response` ;
- `core.errors.ServiceError` ;
- `access.company_module_enabled` ;
- `TenantBase` ;
- le filtre `plain_text`.

**Démonstration.**
- Les 5 annonces du prototype (2 épinglées, lectures).
- Les 4 questionnaires, écrits par les services : ouvert avec 14 réponses, « Intégration » clos avec 3 réponses (résultats masqués, seuil de 5), clos avec 18 réponses, brouillon.
- Écarts : voir `07-donnees-de-demo.md` et L6-15.

**Correctif de stabilité.** L'aide de connexion des parcours attend la fenêtre TOTP suivante si la fenêtre en cours se termine dans moins de 3 s. Un parcours mobile de l'administrateur avait échoué ainsi.

## Corrections de l'audit du lot 6 (25 oct. 2026)

- **Seuil d'anonymat à 5 (L6-17).**
  - Public minimal de 5 personnes ; résultats et commentaires à partir de 5 réponses.
  - Contrainte en base ≥ 5, avec la migration `surveys/0002`, qui porte aussi les questionnaires existants à 5.
  - Raison : à 3, deux répondants qui comparent leurs réponses déduisent celles du troisième.
  - Démonstration : « Intégration » est clos avec 3 réponses (résultats masqués) ; « Enquête télétravail 2025 » est clos avec 18 réponses (résultats visibles).
- **Annonce épinglée supprimée (L6-18).**
  - La suppression retire les notifications dont l'e-mail n'est pas parti, et « Annuler » les recrée sans renvoyer d'e-mail déjà parti.
  - La tâche d'envoi vérifie que l'objet source existe toujours (registre des sources de notification).
- **Caractères invisibles (L6-19).** `apps/core/text.py` retire les caractères de contrôle C0 et C1 et les caractères de mise en forme bidirectionnelle. Il est branché sur tous les `forms.CharField` (sauf les mots de passe) et sur l'import CSV. La règle est ajoutée à CLAUDE.md.
- **Questionnaires.**
  - « Répondre » disparaît après l'échéance.
  - Une confirmation ne s'ouvre que si l'action est possible, avec un message d'état exact (L6-20).
  - « Prolonger l'échéance » est journalisé, seulement tant que l'échéance n'est pas passée ; un questionnaire échu est clos partout (L6-21, corrigé le 26 oct.).
  - Commentaires : 5 par question, puis « Afficher plus » par paquets de 20 (L6-22).
- **Tests.**
  - Test renommé `test_response_keys_do_not_follow_the_order_of_receipts`.
  - Lien résiduel `xmin` documenté par un test, à changer au lot 8.
  - Nouveaux cas : aucun log lors d'une réponse, commentaires à note égale, jour de l'échéance, annonce épinglée supprimée.
- **Qualité.**
  - Chaque `noqa` porte sa raison.
  - Annotations de type sur `actor`, `viewer` et `employee`.
  - Les annonces passent au service un objet `AnnouncementData`.

## Derniers points de la vérification (26 oct. 2026)

- **Course à minuit (L6-23).** Les lectures des résultats prennent un verrou partagé et attendent une réponse en cours. Le test utilise deux connexions réelles ; il échoue sans le verrou.
- **Accessibilité.** Après « Afficher plus », le focus va sur le premier commentaire chargé. Un parcours au clavier le vérifie ; il échoue sans la correction.
- **Code mort.** Les imports `parse_keys` (`accounts/mfa.py`) et `activate_totp` (`planning/tests/test_audit.py`) sont supprimés avec leur `noqa`. RUF100 est active : il reste 19 `noqa`, tous utiles et justifiés.
- **Texte.** U+061C, U+2028 et U+2029 sont retirés aussi.

## Tests

| Commande | Résultat |
|---|---|
| `make lint` | sans erreur |
| `make test` | 771 tests : 769 réussis, 2 sautés (couverture 96 %) ; puis 6 tests de performance (après l'audit du 25 oct. ; 746 réussis avant) |
| `make e2e` | 47 parcours, dont : annonce publiée puis lue (texte affiché sans HTML) ; suppression puis « Annuler » ; questionnaire créé, modifié, publié, rempli, résultats masqués puis visibles après la clôture ; largeur mobile des pages Annonces et Questionnaires pour les 4 profils |
| `make check` | aucune alerte ; `makemigrations --check` avec les réglages de production |

Couverture des modules du lot 6 :
- `announcements` : services 92 %, vues 90 % ;
- `surveys` : services 91 %, sélecteurs 97 %, vues 92 %.

Les deux tests sautés sont les mêmes qu'au lot 5 : S3, sans MinIO local ; relance du transport, qui dépend du jour.

## Critères d'acceptation

| Critère | État |
|---|---|
| Ouvrir une annonce la marque comme lue pour cette seule personne et met à jour le compteur | Fait |
| Un salarié ne voit aucun bouton de gestion et reçoit 403 sur les URL de modification | Fait (manager aussi) |
| Un message contenant `<script>` est affiché comme du texte | Fait (test et parcours) |
| Aucune requête ni aucun export ne relie une réponse à une personne | Fait au niveau de l'application ; risque résiduel L1-09 en base (ordre physique, `xmin` du reçu = `xmin` de la réponse + 1, sauvegardes), documenté par un test |
| Répondre deux fois est impossible, même en renvoyant le formulaire | Fait (contrainte unique) |
| Un commentaire saisi apparaît sous sa question, avec sa note | Fait (après la clôture, L6-01) |
| Avec 2 réponses, les résultats et commentaires sont masqués | Fait (seuil porté à 5 : masqués jusqu'à 4 réponses) |
| Un salarié n'accède pas aux résultats (403) | Fait |

## Écarts au prototype

- Résultats visibles seulement après la clôture (L6-01).
- « Modifier le brouillon » (L6-07).
- Après une action (publier, modifier, supprimer), la page change sans rechargement complet (HX-Location).

## Dette technique

Relevé sur le code des lots 1 à 6. Je n'ai rien repris au-delà de l'étape 0 : chaque point attend ton accord.

### Duplications et incohérences

1. **Erreurs de service.** Six classes identiques (`message`, `field`) : `PeopleError`, `EquipmentError`, `AdministrationError`, `WorkflowError`, `InvitationError`, `ImportFileError`. Seules celles du lot 6 dérivent de `ServiceError`.
2. **Réponse d'erreur et confirmation.**
   - `equipment.views._error`, des `toast_response(Toast(..., kind="err"))` écrits en ligne dans les demandes, l'annuaire et l'administration ;
   - `_confirm_or_act` du matériel, et des dictionnaires recopiés pour `components/confirm.html` ;
   - tout cela fait ce que font `error_response` et `confirm_response`.
3. **Modale de formulaire.** Le motif « modale entière en GET, fragment `#form` et 422 en POST » est recopié dans le matériel, les demandes, l'annuaire et l'administration (`modal_form_response`).
4. **Filtres de liste.** `components/filters.html` existait, mais six listes ont leur formulaire écrit en dur : annuaire, demandes, utilisateurs, journal, planning, matériel.
5. **Traduction des contraintes.** `CONSTRAINT_MESSAGES` et la traduction d'une `IntegrityError` existent trois fois : `approvals.workflow`, `equipment.services`, `people.services`.
6. **Annulation immédiate.** Quatre vues lisent le jeton et affichent l'erreur de la même façon : demandes, matériel, annuaire, annonces.
7. **Module activé dans une tâche.** `approvals/tasks.py` refait la requête de `company_module_enabled`.
8. **Navigation après une action.** Trois façons coexistent :
   - message puis redirection (annuaire, administration) ;
   - événement HTMX qui recharge une zone (matériel, demandes) ;
   - HX-Location (lot 6).
9. **Pluriels.** Il n'y a pas de catalogue `locale/fr` : avec 0, les pluriels suivent la règle anglaise (« 0 collaborateurs »). C'est corrigé à la main dans le lot 6 seulement.
10. **Tests.** La fixture `urls` des parcours est recopiée dans cinq fichiers des lots 1 à 5. Celle du lot 6 est dans `tests/e2e/conftest.py`.

### Fichiers les plus longs (hors tests et migrations)

| Fichier | Lignes |
|---|---|
| `apps/core/management/commands/seed_demo.py` | 1 072 |
| `apps/approvals/workflow.py` | 931 |
| `apps/approvals/views.py` | 641 |
| `apps/equipment/views.py` | 519 |
| `apps/administration/views.py` | 479 |
| `apps/people/views.py` | 442 |

### Fonctions les plus complexes (sous le seuil de 10)

- `ui.control` : 10 ;
- `people.services._update_employee` : 9 ;
- 8 : `approvals.exports.campaign_summary`, `files.clean_image`, `equipment.services.assign`, `people.importer.read`, deux `get` de l'annuaire, `people.views.import_people`, `planning.services._cell`, `planning.services.count_today`.

### Points relevés par l'audit (B2)

11. **Boucles de `notify`.** Les notifications d'un même texte à plusieurs personnes sont créées une à une dans `administration/services.py` (fermeture : RH ou administrateurs) et dans `equipment/services.py` (signalement, archivage d'un détenteur), au lieu de `notify_many`.
12. **Formats de date hors de `dates.py`.**
    - Le journal exporté utilise `strftime("%d/%m/%Y")` et `strftime("%H:%M")` (`administration/services.py`).
    - Les noms de fichiers (`{first:%Y-%m}`) et le calendrier ICS ont des formats techniques. Ceux-là peuvent rester, mais il faut les nommer dans `dates.py`.
13. **Classes d'erreur hors de `ServiceError`.** Huit classes : `WorkflowError`, `AdministrationError`, `PeopleError`, `ExportDeniedError`, `ImportFileError`, `EquipmentError`, `InvitationError`, `UndoError`. `StorageUnavailableError` reste à part : c'est une panne technique, pas un refus métier.
14. **Rendus `#form` avec 422 écrits à la main.** 21 occurrences dans l'administration, le matériel, les demandes et l'annuaire (`modal_form_response`).
15. **`components/confirm.html` rendu directement.** Deux fois dans le matériel (`confirm_response`).
16. **Contexte de l'action.** 27 appels de service passent `actor=request.employee, request=request`. Un petit objet de contexte (personne, adresse IP, requête) passé une seule fois simplifierait les signatures et le journal d'audit.

### Ce que je propose, et quand

- **Avant le lot 7, en un lot de reprise d'environ une journée**, à couverture de tests égale :
  - points 1 à 7 et 10 à 16 : remplacement mécanique par les briques communes ;
  - point 8 : choisir HX-Location comme règle unique de navigation après une action.
- **Au début du lot 7.** Découper `approvals/workflow.py` en transitions, contrôles et campagnes. Le suivi d'intervention réutilise la validation : c'est le bon moment.
- **Lot 8.**
  - Catalogue `locale/fr` (point 9).
  - Découpage de `seed_demo` en un module par domaine.
  - mypy, si tu l'acceptes (ci-dessous).

### Proposition : mypy avec django-stubs (non installé)

- **Intérêt.** Les annotations deviennent vérifiées. mypy attrape les `None` non gérés (9 erreurs `union-attr` aujourd'hui) et les appels avec un mauvais type ou un mauvais argument (dont `trigger(**dict)` dans l'annuaire). Il sécurise les reprises ci-dessus.
- **État mesuré** dans un environnement isolé, sans rien ajouter au projet : mypy 2.4, django-stubs 6.1.2, extension Django, migrations et tests exclus.
  - 117 erreurs dans 22 fichiers ; aucune dans les modules du lot 6.
  - 71 concernent les chaînes traduites paresseuses (`gettext_lazy`) passées là où `str` est attendu (statuts, menu) : une annotation `StrOrPromise` suffit.
  - Le reste : 46 erreurs réelles (types d'arguments, `None`, `objects` sur un type de modèle, variables à annoter).
- **Coût.**
  - Deux dépendances de développement : `mypy` et `django-stubs` (avec `django-stubs-ext`, importé à l'exécution si l'on utilise `StrOrPromise`).
  - Environ une journée pour arriver à 0 erreur.
  - Une étape de plus dans l'intégration continue, avec cache.
- **Proposition.** Ajout bloquant dans l'intégration continue, d'abord sur `services.py` et `selectors.py` (fonctions non annotées interdites), puis étendu au reste.
