# Suivi d'intervention

Le salarié rend compte chaque mois de son travail sur une intervention (mission client ou projet). Menu : groupe « Activité ».

## Écrans

| Route | Écran |
|---|---|
| `/interventions/` | Action « Nouveau compte rendu ». Onglets Mes comptes rendus / À valider (compteur) / Mon équipe (manager) ou Tous les comptes rendus (RH). Filtres : recherche, période, statut. Tableau : collaborateur, intervention, période, avancement (moyenne des travaux réalisés, barre), visibilité, statut, action (Compléter / Valider / Ouvrir) |
| `/interventions/nouveau/`, `/interventions/<id>/modifier/` | Formulaire en page complète (voir ci-dessous), bloc collant : « Envoyer à mon manager », « Enregistrer le brouillon », « Annuler », synthèse (nombre de travaux, destinataire) |
| `/interventions/<id>/` | Compte rendu : statut, bandeau (complément demandé avec la remarque ; validé ; envoyé), indicateurs (avancement moyen, travaux réalisés, travaux prévus, visibilité), sections en lecture, historique ; actions selon le profil et le statut |
| Modale « Valider » | Commentaire facultatif |
| Modale « Demander un complément » | « Ce qu'il faut compléter », obligatoire |

## Formulaire

1. **Intervention :** nom (saisie avec suggestions des interventions déjà utilisées par la personne ; crée une `Mission` si nouvelle), période (mois).
2. **Travaux réalisés sur la période :** blocs répétables « Travail réalisé n », chacun avec Descriptif (obligatoire), Difficultés rencontrées, Solutions proposées, Réalisation en % (obligatoire, 0 à 100), Délai (date), Commentaires. Boutons « Ajouter un travail réalisé » et « Retirer » (au moins un bloc ; retrait annulable).
3. **Travaux prévus pour la période suivante :** blocs répétables avec Description (obligatoire), Réalisation visée en %, Délai, Commentaires.
4. **Visibilité, prolongation et suivi :** Visibilité de l'intervention (Fin prévue, Prolongation probable, Prolongation confirmée, Incertaine), Date de fin prévue, Prolongation souhaitée (Oui/Non), Prolongation jusqu'au (si Oui), Points de suivi, risques et besoins.

Un nouveau compte rendu reprend l'intervention et la visibilité du dernier compte rendu de la personne.

## Règles

- **Brouillon :** seuls l'intervention et la période sont obligatoires ; les pourcentages saisis doivent être des entiers de 0 à 100.
- **Envoi :** tous les champs obligatoires remplis ; au moins un travail réalisé ; visibilité et date de fin renseignées ; prolongation postérieure à la fin prévue (« La prolongation doit aller au-delà de la fin prévue. »).
- Un seul compte rendu par intervention et par période pour une personne (« Un compte rendu existe déjà pour cette intervention et cette période. »).
- **Statuts :** Brouillon → Envoyé → Validé, ou → Complément demandé → (modification) → Envoyé. Seul l'auteur modifie, et seulement en Brouillon ou Complément demandé.
- **Valideur :** manager direct ; RH et administrateur peuvent agir à la place du manager (M-12) ; leur onglet « À valider » ne montre que les personnes sans manager.
- **Repère « Délai dépassé » :** délai passé et réalisation < 100 %.
- La saisie en cours n'est jamais perdue : ajout et retrait de blocs via HTMX sans recharger la page (retrait annulable) ; brouillon enregistré automatiquement toutes les 30 secondes quand la saisie a changé. Chaque enregistrement porte la version lue : depuis une version dépassée (autre fenêtre), rien n'est écrasé et « Ce compte rendu a été modifié dans une autre fenêtre. Rechargez la page. » s'affiche (L7-10).
- **Export PDF** du compte rendu (lot 7) ; tableau de synthèse par intervention pour les RH (plus tard).

## Critères d'acceptation

- Envoyer avec un pourcentage de 150 affiche « Entre 0 et 100 » sous le champ concerné.
- Un compte rendu envoyé n'est plus modifiable par son auteur ; « Complément demandé » le rend de nouveau modifiable et affiche la remarque du manager en tête du formulaire.
- Le manager voit le compte rendu dans « À valider » et dans le compteur du menu ; après validation, il disparaît de l'onglet et l'auteur est notifié.
- Un salarié ne voit pas les comptes rendus d'un collègue (404).
- Ajouter un troisième bloc ne vide pas les deux premiers.
