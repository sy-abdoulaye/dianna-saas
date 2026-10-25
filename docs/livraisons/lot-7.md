# Note de livraison : lot 7, carrière et suivi d'intervention

Date : 25 octobre 2026. Branche : `lot-7`, créée depuis `main` après la fusion de refacto-1 (PR n° 8).

Plan validé le 25 oct. avec les réponses Q1 à Q14 et la correction légale sur l'entretien de parcours professionnel (loi n° 2025-989). Décisions : L7-01 à L7-20 et M-08 dans `00-decisions.md`.

## Ce qui est fait

### Étape 0 : modèles et socle

- Applications `careers` et `interventions`, modèles de `03-modele-de-donnees.md` mis à jour. Tous héritent de `TenantModel`, avec un `public_id` dans les URL et un propriétaire explicite (`employee`).
- Contraintes de base inscrites dans la table commune, chacune avec son message : un entretien en cours par personne et par type, motif cohérent avec le type, note de 1 à 4, compétence et mission uniques sans tenir compte de la casse, un compte rendu par personne, intervention et mois, période au 1er du mois, prolongation après la fin prévue, réalisation de 0 à 100.
- Réglages de l'entreprise : périodicité de l'entretien de parcours (4 ans au plus) et de l'état des lieux (8 ans au plus).
- 4 compétences par défaut à la création d'une entreprise ; migration de données pour les entreprises existantes.
- Permission `careers.manage_campaigns` (RH, administrateur).

### Étape 1 : compétences (administration)

Onglet « Compétences », calqué sur « Services et sites » (le prototype n'a pas d'écran) : ajouter, modifier, monter, descendre (boutons texte, accessibles au clavier), désactiver avec confirmation (notes passées conservées), réactiver. Au moins une compétence reste active. Tout est journalisé.

### Étape 2 : entretiens

- Liste `/carriere/` : indicateurs (campagne terminée, à faire par vous, entretiens planifiés), onglets Entretiens et Fiches de suivi, filtres (`components/filters.html`), pagination.
- Lancement avec annulation immédiate ; campagne d'entretiens par une modale RH.
- Une transition par étape dans `careers/services.py`. Chacune verrouille l'entretien, vérifie l'étape et la personne, notifie la personne suivante et écrit le journal. Les étapes : auto-évaluation ou préparation, évaluation (une note par compétence active, 1 à 5 objectifs en blocs répétables), planification, entretien réalisé, compte rendu du parcours (formations, échéances suggérées, état des lieux à 8 ans au motif « état des lieux »), signatures avec commentaire du salarié.
- Remplacement du manager : bandeau « Vous agissez à la place de {manager} » et « à la place de … » au journal. Sans manager, les RH tiennent le rôle.
- « Relancer » : une fois par entretien et par 24 h (`ratelimit.py`).

### Étape 3 : fiches de suivi

Historique, synthèse (manager, dernier entretien, échéances suggérées), formations. Notes privées visibles par leur seul auteur, par un seul sélecteur (`visible_notes`). Un salarié n'écrit qu'un souhait, sur sa propre fiche. Ajout de note annulable. Raccourci « Fiche de suivi » sur la fiche de l'annuaire (L2-04).

### Étape 4 : comptes rendus d'intervention

- Liste avec Mes comptes rendus, À valider (compteur du menu, identique) et Mon équipe ou Tous les comptes rendus.
- Formulaire en page complète :
  - blocs répétables : l'ajout ne renvoie que le nouveau bloc, le retrait est annulable ;
  - brouillon partiel, contrôles complets à l'envoi ;
  - enregistrement automatique versionné (L7-10).
- Détail : indicateurs, repère « Délai dépassé », historique.
- Décisions et annulations :
  - validation et demande de complément, « à la place de » pour un RH ;
  - annulation immédiate de l'envoi et des décisions.

### Étape 5 : exports PDF

Entretien, fiche de suivi (jamais de note privée) et compte rendu passent par une nouvelle brique, `pdf.pdf_response` : même récupérateur d'URL fermé et même limite de fréquence que le planning. Ils utilisent la feuille A4 portrait `pdf-document.css`, et le journal ne porte aucun nom de personne.

### Étape 6 : tableau de bord et démonstration

- Tableau de bord :
  - « À traiter » : entretiens à compléter, comptes rendus à valider ou à envoyer ;
  - indicateurs « Entretiens à mener » (manager) et « Campagne d'entretiens » (RH) ;
  - raccourci Carrière.
- Démonstration :
  - 10 entretiens à toutes les étapes, une campagne, les notes du prototype dont la note privée de Louise ;
  - 4 comptes rendus : validé, brouillon, envoyé, complément demandé ;
  - un module `demo.py` par application, appelé par `seed_demo`, qui ne grossit que de 6 lignes.

### Briques communes ajoutées ou évoluées

- `apps/core/repeatable.py`, la vue `core:add_block` et `components/repeatable.html` : blocs répétables. Le retrait et son « Annuler » se font dans `ui.js`.
- `fields.PercentTextField` : pourcentage saisi en texte, jamais `type="number"`.
- `http.attachment` et `pdf.pdf_response`. `attachment` remplace aussi les trois téléchargements écrits à la main : exports RH, planning, journal.
- `components/field.html` : `required_mark` (obligatoire à l'envoi seulement) et `suffix` (« % »).
- Notification visuelle : « Annuler » côté navigateur (`onUndo`), en plus du jeton du serveur.
- Les nouveaux `services.py` et `selectors.py` entrent automatiquement dans le périmètre bloquant de mypy : 23 fichiers, annotations complètes.

### Correction de la coque (25 oct., après les tests de Leo)

- **Cause mesurée** (Playwright, `/interventions/nouveau/`, 1920×1080) : la zone `.main` défilait sur 2 118 px, mais le document faisait aussi 1 874 px. La légende `.sr-only` du sélecteur « Prolongation souhaitée » et ses deux boutons radio sont en position absolue, sans ancêtre positionné : leur bloc conteneur était la page entière. Placés à 1 873 px, ils allongeaient le document hors de la zone qui défilait. D'où deux défilements, et un menu latéral (100 % de la hauteur) arrêté à mi-écran une fois le document défilé.
- **Nouvelle coque** (`layouts/app.html`, `app.css`, `ui.js`) :
  - `.app` est la seule hauteur d'écran (100dvh), en grille : en-tête fixe en haut, menu latéral et zone principale dessous ;
  - `.main`, positionnée, est le seul conteneur à défilement vertical ;
  - le document ne défile plus.
- **Hamburger** : rail d'icônes mémorisé à partir de 1 024 px ; en dessous, tiroir avec voile, Échap, piège du focus et page inerte derrière.
- **Barre d'étapes** : elle ne défile plus horizontalement ; sous 640 px, elle passe en colonne.
- **Contrôle automatique** (`tests/e2e/test_layout.py`) :
  - toutes les entrées du menu des 4 profils, plus des pages longues et des états vides, à 1920×1080, 1440×900, 1280×720 et 390×844, en clair et en sombre ;
  - parcours du rail (repli, dépli, état conservé après rechargement) et du tiroir mobile.

## Règles légales (M-08) : ce qui reste à confirmer par un juriste

L'implémentation suit la loi n° 2025-989 du 24 octobre 2025 (article L6315-1 modifié) et le questions-réponses du ministère du Travail mis à jour en février 2026, résumés dans M-08 et la fiche 10 :

- premier entretien dans la première année de présence ;
- puis tous les 4 ans au plus ;
- état des lieux à 8 ans avec 3 critères ;
- abondement apprécié sur 8 ans, non calculé par Dianna ;
- mi-carrière et fin de carrière lancées par le RH, sans date de naissance stockée.

**À confirmer** :
- les absences qui ouvrent droit à l'entretien de retour ;
- les délais exacts de mi-carrière et de fin de carrière ;
- le contenu attendu de l'état des lieux ;
- la remise d'une copie écrite au salarié ;
- l'appréciation de l'abondement ;
- les durées de conservation (M-13) ;
- le droit d'accès du salarié aux notes privées le concernant (export RGPD, lot 8).

## Écarts au prototype

- « Entretien professionnel » devient « Entretien de parcours professionnel » (L7-01).
- « Notez les quatre compétences de 1 à 4. » devient « Notez toutes les compétences de 1 à 4. » (L7-15).
- Lieu de l'entretien : texte libre avec suggestions, au lieu de salles en dur (L7-09).
- Synthèse du formulaire de compte rendu : « Envoyé à » seulement. Le prototype compte aussi les blocs en direct, ce qui demanderait du JavaScript de plus pour une information déjà visible.
- Écrans sans modèle dans le prototype, faits avec les composants existants : onglet Compétences, modale de campagne, bloc État des lieux à 8 ans, réglages du parcours.

## Tests

| Commande | Résultat |
|---|---|
| `make lint` | sans erreur (ruff, ruff format, djlint : 151 gabarits) |
| `make typecheck` | 23 fichiers, aucune erreur (annotations complètes) |
| `make test` | 951 tests : 949 réussis, 2 sautés (S3 sans MinIO local ; relance du transport, qui dépend du jour) ; couverture 96 % (services de la carrière 96 %, des interventions 97 %, `permissions.py` 99 %) ; puis 6 tests de performance |
| `make e2e` | 76 parcours (12 nouveaux, dont 6 pour la coque et le hamburger) |
| `make check` | aucune alerte, aucune migration manquante |

Nouveaux tests :
- services de la carrière (27) et des interventions (15) ;
- écrans de la carrière (27), des interventions (17), des compétences (4) ;
- tableau de bord (3), briques communes (12) ;
- batterie d'isolation : 11 nouveaux modèles, 22 nouvelles routes ;
- 6 parcours Playwright : parcours 3 et 7, blocs répétables, allers-retours.

Le parcours 3 a révélé un défaut, corrigé : le bouton « Marquer l'entretien comme réalisé » héritait du `hx-swap` du formulaire de l'étape et ne pouvait pas ouvrir sa confirmation.

## Dette technique

### Duplications et incohérences

- **« à la place de … » au journal** : trois écritures voisines. `approvals.workflow.transitions._substitution`, `careers.services._audit` et `interventions.services._audit` construisent chacune ce suffixe. Proposition : une brique `audit.replacement_suffix(actor, manager)` au lot 8.
- **Onglets des listes** : la liste de dictionnaires `{label, url, count, active}` est construite à la main dans cinq vues (demandes, matériel, carrière, interventions, annuaire). Proposition : un assistant `ui.tabs(url, [(clé, libellé, compteur)], actif)`.
- **Valideur d'un compte rendu** : il réutilise `workflow.active_manager` et `workflow.hr_validators`. Les comptes rendus ne sont pas des demandes du moteur : choix assumé, car leurs états diffèrent (brouillon versionné, complément demandé).

### Fichiers les plus longs (hors tests et migrations)

`seed_demo.py` 1 078 lignes, `careers/services.py` 630, `approvals/views.py` 612, `careers/views.py` 579, `administration/views.py` 571, `equipment/views.py` 510.

`careers/services.py` mêle entretiens, notes, campagnes et compétences. Proposition : en sortir les compétences et les campagnes (`careers/settings_services.py`) si le fichier grossit encore.

### Complexité

Aucune nouvelle fonction au-dessus de 6. La seule au-dessus de 6 dans le code touché est `dashboard._employee_indicators` (7), déjà présente.

### Exceptions `noqa`

20, inchangé.

### Reste pour le lot 8

- Export RGPD et notes privées (juriste).
- Conservation des entretiens et des notes (M-13).
- Préférences de notification : seuls « entretien lancé » et « compte rendu à valider » partent par e-mail (M-16).
- Délégation nominative du manager.
- Tableau de synthèse des interventions pour les RH (« plus tard » dans la fiche 11).
