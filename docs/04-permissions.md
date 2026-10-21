# Permissions

Colonne « Manager » : elle s'applique à toute personne qui a des collaborateurs directs, quel que soit son profil (L1-02). Le profil « Manager » seul n'ajoute aucun droit.

Légende : **Oui** = autorisé ; **Équipe** = limité aux fiches dont la personne est le manager direct ; **Soi** = ses propres données ; **Non** = interdit et non affiché.

Règles générales :
- Un utilisateur n'accède qu'aux données de son entreprise (404 sinon).
- Personne ne valide sa propre demande.
- Une note privée de suivi n'est visible que par son auteur, y compris pour les RH.
- Les réponses aux questionnaires ne sont jamais rattachées à une personne.
- Le super-administrateur éditeur n'a pas d'accès aux données métier, sauf accès support explicite, limité dans le temps et journalisé (lot 8).

## Annuaire

| Action | Salarié | Manager | RH | Admin |
|---|---|---|---|---|
| Voir la liste et les coordonnées professionnelles des salariés en poste | Oui | Oui | Oui | Oui |
| Voir les fiches au statut « Parti » | Non | Non | Oui | Oui |
| Voir les informations RH (contrat, matricule, temps de travail) | Soi | Soi | Oui | Oui |
| Modifier son téléphone et son bureau | Soi | Soi | Oui | Oui |
| Créer, modifier, archiver, réactiver une fiche | Non | Non | Oui | Oui |
| Archiver une fiche de profil Administrateur (« Seul un administrateur peut archiver un administrateur. ») | Non | Non | Non | Oui |
| Attribuer un profil d'accès | Non | Non | Non | Oui |
| Importer des salariés (CSV) | Non | Non | Non | Oui |

## Demandes (télétravail, congés, astreintes)

| Action | Salarié | Manager | RH | Admin |
|---|---|---|---|---|
| Créer, voir, annuler ses demandes en attente (y compris « Validée par le manager ») | Soi | Soi | Soi | Soi |
| Voir les demandes | Soi | Équipe | Oui | Oui |
| Valider ou refuser | Non | Équipe | Oui, sur toute demande (remplacement, M-12) ; « À valider » ne montre que les personnes sans manager | Comme RH |
| Annuler une demande validée, avec motif (L3-10) | Non | Non | Oui, sauf sa propre demande | Oui, sauf sa propre demande |
| Annulation immédiate (« Annuler » dans la notification, 30 s) | Auteur de l'action seulement | Auteur seulement | Auteur seulement | Auteur seulement |
| Voir l'alerte de conflit d'absences (noms et nombre) | Non, jamais sur ses propres demandes | Si peut décider (équipe directe) | Si peut décider (à la place du manager ou étape RH) | Comme RH |
| Gérer les campagnes de congés d'été (`/conges/campagnes/`) | Non | Non | Oui | Oui |
| Validation finale des congés d'été (M-03) | Non | Non | Oui | Oui |
| Exporter (paie) | Non | Non | Oui | Oui |

Personne ne décide pour soi-même ni n'annule sa propre demande validée (`SELF_FORBIDDEN`). L'annulation immédiate est liée à l'auteur par un jeton signé ; elle est refusée si une autre décision a suivi (A3-01). L'alerte de conflit n'est calculée que pour qui peut décider sur la demande (A3-03).

## Transport et matériel

| Action | Salarié | Manager | RH | Admin |
|---|---|---|---|---|
| Déposer un justificatif, demander du matériel, signaler un problème | Soi | Soi | Soi | Soi |
| Voir le justificatif d'un autre salarié | Non | Non | Oui | Oui |
| Valider les justificatifs et les demandes de matériel | Non | Non | Oui | Oui |
| Voir le matériel de son équipe | Non | Équipe | Oui | Oui |
| Gérer le parc (ajouter, attribuer, restituer, réparation) | Non | Non | Oui | Oui |

## Planning

| Action | Salarié | Manager | RH | Admin |
|---|---|---|---|---|
| Voir le planning | Son service | Son service et son équipe directe (L1-06) | Toute l'entreprise | Toute l'entreprise |
| Exporter le planning (CSV, Excel, iCalendar, PDF) | Son service | Son service et son équipe directe | Oui, entreprise ou un service | Comme RH |
| Voir les fermetures et jours fériés | Non | Non | Oui (lecture) | Oui |

**Ce que montre une case (L4-16, minimisation).**

| Qui regarde | Ses propres journées | Son équipe directe (manager) | Toute personne du périmètre (RH, administrateur) | Un collègue du périmètre |
|---|---|---|---|---|
| Congés | Type exact, en attente compris | Type exact, en attente compris | Type exact, en attente compris | « Absent », validés seulement |
| Télétravail | En attente compris | En attente compris | En attente compris | Validé seulement |
| Astreinte (repère « A ») | En attente compris | En attente compris | En attente compris | Validée seulement |

La règle vaut pour la vue, l'aperçu de l'export et les fichiers CSV, Excel, iCalendar et PDF. Le bloc « Aujourd'hui » du tableau de bord ne montre que des nombres.

Le filtre de service n'est proposé qu'aux RH et administrateurs ; pour les autres, un service passé dans l'URL ne fait que restreindre leur périmètre, et un périmètre d'export hors de leurs choix est refusé (400). Chaque export est inscrit au journal d'audit (L4-12).

Exports RH des demandes (`requests.export`, L4-09) : récapitulatif mensuel du télétravail, export paie des astreintes, synthèse de campagne. Salarié et manager : non ; RH et administrateur : oui.

## Carrière et évaluations

| Action | Salarié | Manager | RH | Admin |
|---|---|---|---|---|
| Voir ses entretiens et sa fiche de suivi | Soi | Soi | Soi | Soi |
| Voir les entretiens et fiches de l'équipe | Non | Équipe | Oui | Oui |
| Lancer un entretien | Non | Équipe | Oui | Oui |
| Remplir l'auto-évaluation ou la préparation | Soi | Soi | Soi | Soi |
| Remplir l'évaluation, planifier, marquer réalisé | Non | Équipe | Oui (remplaçant) | Oui (remplaçant) |
| Signer | Soi (salarié) | Équipe (manager) | Oui, à la place du manager absent | Comme RH |
| Ajouter une note de suivi | « Souhait » sur soi | Équipe (peut être privée) | Oui | Oui |

## Questionnaires

| Action | Salarié | Manager | RH | Admin |
|---|---|---|---|---|
| Répondre aux questionnaires ouverts qui le concernent | Oui | Oui | Oui | Oui |
| Voir les résultats agrégés (au-delà du seuil d'anonymat) | Non | Oui | Oui | Oui |
| Créer, publier, clore, supprimer un brouillon | Non | Non | Oui | Oui |

## Communication interne

| Action | Salarié | Manager | RH | Admin |
|---|---|---|---|---|
| Lire les annonces | Oui | Oui | Oui | Oui |
| Publier, modifier, épingler, supprimer ; voir le taux de lecture | Non | Non | Oui | Oui |

## Suivi d'intervention

| Action | Salarié | Manager | RH | Admin |
|---|---|---|---|---|
| Créer, modifier (brouillon ou complément demandé), envoyer ses comptes rendus | Soi | Soi | Soi | Soi |
| Voir les comptes rendus | Soi | Équipe | Oui | Oui |
| Valider ou demander un complément | Non | Équipe | Oui, sur tout compte rendu (remplacement, M-12) ; « À valider » ne montre que les personnes sans manager | Comme RH |

## Administration

La gestion des compétences d'entretien (lot 7) fait partie de l'administration.

| Action | Salarié | Manager | RH | Admin |
|---|---|---|---|---|
| Paramètres de l'entreprise, services et sites, modules, profils, journal | Non | Non | Non | Oui |
| Fermetures (onglet « Fermetures ») : consulter | Non | Non | Oui (seul onglet visible) | Oui |
| Fermetures : ajouter, supprimer | Non | Non | Non | Oui |
