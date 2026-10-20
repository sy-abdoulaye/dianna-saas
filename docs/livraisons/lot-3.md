# Note de livraison : lot 3, demandes et validation

Date : 20 octobre 2026. Branche : `lot-3`.

## Ce qui est fait

**Tâches en arrière-plan (T-11, L3-01).**
- `django-tasks-db` 0.13.0 épinglé.
- Travailleur `make worker`, à lancer en développement, et `python manage.py db_worker` en production ; documenté dans le LISEZ-MOI.
- Tous les e-mails passent par une tâche : invitations, mot de passe oublié, lien de la vitrine, demandes.
- Les e-mails d'une action annulable partent après 45 s, et seulement si l'action n'a pas été annulée.
- Les tests passent par le vrai travailleur.

**Moteur commun (`apps/approvals/workflow.py`).**
- Une fonction par transition : envoi, validation, validation du manager, refus avec motif, annulation par le demandeur, annulation d'une demande validée par les RH avec motif (L3-10), annulation immédiate.
- Verrouillage de la demande en base : deux clics rapides font une seule transition, ce qu'un test de concurrence vérifie avec deux connexions réelles.
- Valideur : manager direct, sinon RH et administrateurs autres que le demandeur, sinon validation automatique tracée (M-12).
- Étape RH des congés d'été (M-03, L3-02, L3-03), validation automatique du télétravail (M-02).
- Effets de chaque transition :
  - événement de calendrier : en attente dès l'envoi, validé à la décision finale, supprimé sinon ;
  - historique de la demande ;
  - notifications ;
  - journal d'audit.

**Écrans.**
- Télétravail, Congés estivaux et Astreintes sur un gabarit commun : onglets Mes demandes, À valider (avec compteur), Mon équipe ou Toutes les demandes, filtres, modales.
- Contrôles et messages du prototype.
- Conflits d'absence avec alerte renforcée au-delà du seuil.
- Bandeau « Vous agissez à la place de … » quand un RH ou un administrateur remplace le manager.
- Campagnes de congés d'été (RH).
- Compteurs « à traiter » dans le menu ; onglet « Demandes » de la fiche annuaire.
- Page « Module désactivé » sur toutes les adresses des trois modules, le point resté partiel au lot 2.

**Démonstration.** Demandes du prototype : télétravail sur deux semaines, campagne « Été 2027 » avec conflit au Support client, astreintes et interventions.

## Corrections de l'audit (A3-01 à A3-06)

- **Annulation immédiate** : le jeton porte l'événement de la transition ; refusée (409) si une autre décision a été prise depuis, sans rien modifier.
- **Contrôles métier dans le service** : quota, même jour, chevauchements, période de campagne, sous verrou de la fiche du demandeur, à l'envoi et aux annulations immédiates qui réactivent une demande (annulation, annulation d'une demande validée, refus). Aucune `IntegrityError` ne produit d'erreur 500.
- **Alerte de conflit** : visible seulement pour qui peut décider ; plus de nombre d'absences dans la notification d'envoi.
- **Tâches** : identifiants seulement pour les e-mails de Dianna, jeton d'invitation créé dans la tâche, e-mails d'allauth chiffrés (`TASKS_ENCRYPTION_KEY`). Résultats réussis supprimés aussitôt, échecs purgés après 7 jours (`purge_task_results`, service `scheduler`).
- **Notifications devenues fausses** : supprimées à chaque transition si leur e-mail n'est pas parti ; les valideurs sont prévenus de nouveau quand une annulation immédiate remet la demande en attente.
- **Campagnes** : ouverture sous verrou ; deux ouvertures simultanées donnent une seule campagne ouverte.
- Tests dans `apps/approvals/tests/test_audit.py` (dont cinq tests de concurrence à deux connexions) et `apps/core/tests/test_tasks.py`.

## Vérification de contrôle (21 oct. 2026)

- L3-13 appliquée : à l'étape « Validée par le manager », le demandeur est prévenu dans Dianna seulement ; les RH reçoivent l'e-mail.
- Invitation : l'empreinte du jeton n'est enregistrée qu'après l'acceptation de l'e-mail par le serveur d'envoi ; en cas d'échec, l'invitation précédente reste valable et la nouvelle est marquée « Envoi échoué » dans « Utilisateurs et profils », avec « Renvoyer l'invitation ».
- Création des campagnes par un service, comme l'ouverture et la clôture.
- `seed_demo` : notifications liées à leur demande ; contrôles métier sur les demandes de démonstration à venir (seules les demandes passées en sont dispensées).
- Profil `taches` de Docker Compose : configuration lue dans `.env`, réservé au développement et aux essais ; déploiement du travailleur et de la purge au lot 8.
- Documentation alignée : 00-decisions (L1-14, T-11, A3-04, « Pour plus tard »), 02-architecture, 03-modele-de-donnees, 04-permissions, fiche 05, CLAUDE.md.

## Corrections finales (21 oct. 2026)

- Profil Compose `taches` : réglages de développement, base `db` forcée, migrations avant le travailleur et la purge ; démarrage vérifié avec un `.env` créé par `make install`.
- Critère d'acceptation : l'annulation d'une validation finale RH ramène la demande à « Validée par le manager ».
- Invitations : un échec de confirmation après l'envoi donne « Envoi échoué » ; la confirmation vérifie sous verrou que l'invitation n'a pas été remplacée entre-temps.

## Tests

| Commande | Résultat |
|---|---|
| `make lint` | sans erreur |
| `make test` | 439 tests (21 octobre 2026, après les corrections finales) ; couverture 95 % au total, de 88 à 100 % sur `approvals` |
| `make e2e` | 34 parcours, dont les parcours 1 et 2 et la page « Module désactivé » |
| `make check` | aucune alerte, dont `--deploy` |

## Critères d'acceptation (fiche 05)

| Critère | État |
|---|---|
| Troisième jour de télétravail refusé, avec la semaine et le maximum | Fait |
| « À valider » du manager limité à son équipe directe ; pas de validation de sa propre demande | Fait |
| Refus sans motif bloqué ; motif dans l'historique du demandeur | Fait |
| Événement de planning en attente à l'envoi, validé à la validation finale, supprimé au refus ou à l'annulation | Fait |
| « Annuler » après une validation : demande en attente, notification retirée | Fait |
| Deux clics rapides sur « Valider » : une seule transition | Fait (test de concurrence réel) |
| Justificatifs de transport (6 Mo, .exe, URL d'un collègue) | Lot 5 |

## Écarts et points à relire

- Décisions L3-12 à L3-18 validées le 21 octobre 2026. Les jours fériés et les fermetures seront exclus du télétravail au lot 4, avec le planning (L3-12).
- Les exports RH sont au lot 4 (L3-08).
- Dépendance ajoutée : `django-tasks-db` 0.13.0, avec la réserve sur Django 6.1 (L3-01).
