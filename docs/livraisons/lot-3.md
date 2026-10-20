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

## Tests

| Commande | Résultat |
|---|---|
| `make lint` | sans erreur |
| `make test` | 408 tests ; couverture 95 % au total, de 86 à 96 % sur `approvals` |
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

- Décisions L3-12 à L3-18 dans `00-decisions.md` (« À confirmer »). La principale : les jours fériés ne sont pas encore exclus du télétravail (planning, lot 4).
- Les exports RH sont au lot 4 (L3-08).
- Dépendance ajoutée : `django-tasks-db` 0.13.0, avec la réserve sur Django 6.1 (L3-01).
