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

## Tests

| Commande | Résultat |
|---|---|
| `make lint` | sans erreur |
| `make test` | 638 tests (couverture 95 %), dont le test S3 sauté sans MinIO local et exécuté dans l'intégration continue ; puis 6 tests de performance |
| `make e2e` | 40 parcours, dont le dépôt d'un justificatif puis sa validation par les RH (téléchargement du fichier), et l'attribution d'un équipement puis « Annuler » |
| `make check` | aucune alerte, dont `--deploy` (configuration S3 vérifiée) |

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

- Décisions « À confirmer » :
  - L5-02, pour l'image MinIO de l'intégration continue : les images officielles de MinIO ne sont plus publiées, d'où `bitnamilegacy/minio:2025.7.23` ;
  - L5-10 : réparation ;
  - L5-13 : export paie ;
  - L5-15 : signalements.
- L'analyse antivirus (ClamAV), notée « à confirmer » pour le lot 5 dans `02-architecture.md`, n'est pas faite. Elle est reportée au lot 8 dans « Pour plus tard », avec la création du compte Scaleway, le mode de chiffrement à vérifier, la purge à 3 ans et les limites internes d'allauth.
