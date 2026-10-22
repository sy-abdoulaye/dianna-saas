# Note de livraison : lot 5, transport et matériel

Date : 21 octobre 2026. Branche : `lot-5`.

## Ce qui est fait

**Stockage des fichiers privés (T-12, L5-02).**
- Un seul stockage privé, choisi par `PRIVATE_STORAGE_BACKEND` :
  - disque en développement et dans les tests ;
  - S3 en production : Scaleway Object Storage (fr-par), `django-storages[s3]` 1.14.6 et `boto3` 1.43.116.
- Un bucket privé par environnement, chiffrement côté serveur, identifiants en variables d'environnement documentées dans `.env.example`.
- `manage.py check --deploy` vérifie la configuration.
- Le compte Scaleway sera créé au lot 8.
- L'intégration continue teste le vrai stockage S3 sur MinIO, chiffrement activé : objet chiffré, aucun accès anonyme, lecture seulement par la vue qui contrôle la permission.

**Justificatifs de transport (fiche 05, section Transport).**
- Nouveau type du moteur commun, validé par les RH et l'administrateur, sans étape manager (L5-04).
- `valid_until` est calculé.
- Contrôles, faits par le service sous verrou de la fiche (A3-02) :
  - mois (des 12 derniers au mois prochain) ;
  - montant ;
  - chevauchement des abonnements mensuels et annuels (L5-06).
- Fichier :
  - type réel vérifié sur le contenu, pas sur l'extension ;
  - 5 Mo, lus par morceaux ;
  - images réencodées sans métadonnées, position GPS comprise ;
  - seuls les PDF chiffrés sont refusés (L5-03) ;
  - stocké sous `<company_id>/transport/<aléatoire>`, jamais sous son nom d'origine.
- Service du fichier (L5-01) :
  - seulement après contrôle de la permission, à chaque téléchargement, jamais par lien signé ;
  - réponse isolée : type exact, `nosniff`, `sandbox`, pas de cache partagé ;
  - nom d'origine échappé dans `Content-Disposition` ;
  - toute consultation par un RH ou un administrateur est inscrite au journal.
- Détail pour les RH : image affichée, PDF ouvert dans un nouvel onglet, « Télécharger », validité et remboursement estimé.
- Bloc d'information avec la justification légale : article L3261-2 du Code du travail.
- Export paie mensuel (CSV, Excel) : un douzième par mois pour un abonnement annuel, 50 % de remboursement, titre unique « Non concerné » (L5-13).
- Relance 15 jours avant la fin d'un abonnement annuel : notification et e-mail, une seule fois. `enqueue_daily_tasks` met la tâche en file, et le travailleur l'exécute (L5-12).
- Fichier supprimé si l'envoi est retiré dans les 30 s ou interrompu par une erreur (L5-05).

**Suivi du matériel (fiche 07).**
- Onglets : Mon matériel, Mon équipe (manager, lecture seule), Parc, Demandes, Signalements.
- Parc : indicateurs, filtres (les équipements retirés sont masqués par défaut), historique par équipement.
- Actions : ajouter, attribuer (annulable pendant 30 s), restituer, réparation, fin de réparation, retirer du parc.
- Un seul détenteur, garanti en base (L5-08) : index unique partiel (une attribution ouverte par équipement), contrainte état et détenteur, une attribution au plus par demande. Les services verrouillent l'équipement ; un test de concurrence à deux connexions le vérifie.
- Demandes de matériel : passent par le moteur commun et sont validées par les RH. Une demande validée affiche « Attribuer un équipement » (stock du type demandé).
- Signalements : faits par le détenteur, RH prévenus, envoi en réparation (détenteur conservé), clôture avec résolution.
- Archivage d'un détenteur : alerte dans la confirmation et notification aux RH avec la liste ; l'archivage n'est pas bloqué (L5-11).

**Tableau de bord.** Apparaissent les indicateurs « Matériel attribué » et « Justificatifs à valider », les lignes « À traiter » de ces modules et le raccourci « Mon matériel ».

**Démonstration.** Données du prototype :
- justificatifs, avec de petits fichiers PDF et JPG générés ;
- demandes de matériel ;
- parc de 15 équipements avec attributions et historique.

**Correctif transversal (L5-16).** L'en-tête `HX-Trigger` est désormais écrit en JSON ASCII. Un « € » dans une notification visuelle le rendait illisible pour htmx : Django encode les caractères hors Latin-1 selon la RFC 2047.

## Corrections de l'audit du lot 5 (21 oct. 2026)

- **Stockage indisponible (L5-17).**
  - Délais explicites : connexion 3 s, lecture 10 s, 2 essais au total. Attention : dans botocore, `max_attempts` ne compte que les nouvelles tentatives ; c'est `total_max_attempts` qui compte tous les essais.
  - Dépôt d'un justificatif : 503 avec le message, rien n'est enregistré.
  - Téléchargement : page 503.
  - Photos et logo : plus d'`exists()` ; si le stockage échoue, l'avatar garde ses initiales et le logo est masqué.
  - Test réel avec un stockage injoignable : l'annuaire et une photo répondent en 6,6 s au total, sans erreur 500.
- **Fichiers orphelins (L5-18).**
  - Le nom du fichier est inscrit dans la liste de nettoyage avant l'écriture, et le fichier est écrit avant l'INSERT puis supprimé si l'opération échoue.
  - Une DataError à l'INSERT donne un message, sans laisser de fichier.
  - Même règle pour les photos et le logo : l'ancien fichier n'est supprimé qu'après la validation. La règle est ajoutée à CLAUDE.md.
- **PDF chiffrés.** Les échappements `#xx` des noms PDF sont décodés : `/Encr#79pt` est reconnu (L5-03).
- **Contrôles dans le service (L5-19).**
  - La fenêtre de mois et les bornes du montant sont vérifiées par le service.
  - Chaque IntegrityError est traduite selon la contrainte en cause, pour les demandes comme pour le matériel.
- **Numéro de série (L5-09).** Normalisé dans le service (NFKC, sans espaces ni espaces insécables, majuscules), avec une contrainte unique sur la valeur normalisée et une migration de normalisation.
- **Intégration continue.** L'image MinIO est épinglée par son empreinte. Son remplacement est noté pour le lot 8, de même que l'analyse antivirus au dépôt, avant l'enregistrement.

## Vérification élargie du lot 5 (22 oct. 2026)

- **Nombres décimaux (L5-20).**
  - Le montant d'un justificatif et la durée d'une intervention sont des champs texte avec `inputmode="decimal"`.
  - « 2,15 » et « 2.15 » donnent 2,15 ; tout autre format est refusé (« Saisissez un montant comme 84,10. »), puis les bornes sont vérifiées.
  - Champ commun : `apps/core/fields.DecimalTextField`.
- **Stockage.**
  - Les modèles passent la fonction `get_private_storage` : les migrations ne dépendent plus du réglage, sans changement de schéma.
  - `make check`, lancé par l'intégration continue, vérifie `makemigrations --check` avec les réglages de production et la configuration S3.
  - Coupe-circuit par processus (L5-21) : après une panne, les appels suivants échouent aussitôt pendant 30 s. Avec S3 injoignable, 12 photos font un seul appel au stockage (deux essais réseau, ceux de botocore) au lieu de 12.
- **Numéros de série.** La migration de normalisation détecte les doublons avant la contrainte unique :
  - le premier garde son numéro, les suivants reçoivent « -DOUBLON-2 », « -DOUBLON-3 »… ;
  - la liste est affichée et inscrite au journal d'audit de l'entreprise ;
  - test avec « AB 123 », « ab123 » et « ＡＢ１２３ ».
- **Types validés par les RH.** Le message d'envoi dit « transmise aux RH », et le journal n'écrit jamais « à la place de ».
- **Annuaire.** Une adresse e-mail en double qui atteint la base (deux créations simultanées) donne un message sur le champ, pas une erreur 500.
- **Dates (L5-22).**
  - Une seule fonction pour tout le projet, `apps/core/dates.format_date`, avec le filtre `fr_date`.
  - Elle écrit « 1er novembre », y compris dans la relance.
  - « mer. 21 oct. » dans les lignes de demandes, « lun. 19 oct. » dans les en-têtes du planning.
- **Mobile (L5-23).** À 390 px, aucune page ne dépasse l'écran : le planning, l'annuaire, les campagnes et les utilisateurs défilent dans leur conteneur. Cause : le texte `sr-only` des tableaux, en position absolue, n'était pas retenu par le conteneur qui défile. Un parcours vérifie 27 pages pour les 4 profils.
- **Écarts avec le prototype.**
  - « Rechercher dans mes demandes », dans le résumé des demandes, sur les quatre modules.
  - Résumé d'un justificatif dans l'ordre du prototype : mois · type · montant · nom du fichier.
  - Colonne « Attribué à », avec la date, dans « Mon matériel ».
  - « Envoyer en réparation » demande une confirmation et s'annule pendant 30 s, depuis le parc comme depuis un signalement.
  - Un équipement seul de son type en stock est présélectionné dans « Attribuer un équipement ».
- **Documentation.**
  - Règle 5 de CLAUDE.md : un justificatif n'est jamais servi par lien signé (L5-01).
  - LISEZ-MOI : `APP_PORT`, `DB_PORT` et `COMPOSE_PROJECT_NAME`, et `make seed` dans l'enchaînement des commandes.
  - `00-decisions.md` : nouvelle section « V2, à décider après le lot 8 ».

## Tests

| Commande | Résultat |
|---|---|
| `make lint` | sans erreur |
| `make test` | 686 tests : 684 réussis, 2 sautés (couverture 95 %) ; puis 6 tests de performance. Les deux tests sautés : le test S3, sans MinIO local, est exécuté dans l'intégration continue ; la relance par le travailleur dépend du jour (la relance elle-même est aussi testée à date fixe) |
| `make e2e` | 44 parcours, dont le dépôt d'un justificatif saisi « 2,15 » puis sa validation par les RH (téléchargement du fichier), l'attribution d'un équipement puis « Annuler », et la largeur mobile pour les 4 profils |
| `make check` | aucune alerte, dont `--deploy` (configuration S3 vérifiée) et `makemigrations --check` avec les réglages de production |

Couverture des nouveaux modules : `apps/equipment` de 91 à 100 %, `apps/core/files.py` 91 %, `apps/approvals/tasks.py` 91 %.

## Critères d'acceptation

| Critère | État |
|---|---|
| Un justificatif de 6 Mo ou au format .exe est refusé avec un message explicite | Fait |
| Un salarié ne peut pas télécharger le justificatif d'un collègue, même avec l'URL | Fait (404 ; son manager non plus) |
| Un salarié ne voit pas l'onglet Parc et reçoit 403 sur ses URL | Fait |
| Attribuer puis « Annuler » remet l'équipement en stock et retire la notification | Fait (test et parcours) |
| Archiver un salarié qui détient un ordinateur affiche l'alerte de restitution | Fait |

## Image Docker

`lot-4` : 742 Mo ; `lot-5` : 845 Mo (+103 Mo, essentiellement `botocore`).

## Points à relire

- Décisions L5-02 (image MinIO comprise), L5-10 et L5-15 : validées le 22 oct. 2026.
- L'analyse antivirus (ClamAV), notée « à confirmer » pour le lot 5 dans `02-architecture.md`, n'est pas faite. Elle est reportée au lot 8 dans « Pour plus tard », avec la création du compte Scaleway, le mode de chiffrement à vérifier, la purge à 3 ans et les limites internes d'allauth.
