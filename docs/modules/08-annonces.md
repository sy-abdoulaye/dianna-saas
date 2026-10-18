# Communication interne

| Route | Écran |
|---|---|
| `/annonces/` | Sous-titre « N annonces non lues » ou « Vous avez tout lu ». Filtres : recherche, catégorie (Entreprise, RH, Vie du site, Sécurité). Liste : point bleu si non lue, catégorie, « Épinglée », date, auteur, titre (gras si non lue), extrait de 140 caractères. Épinglées en premier, puis par date. Action RH : « Nouvelle annonce » |
| `/annonces/<id>/` | Lecture (marque comme lue). RH : Épingler/Désépingler, Modifier, Supprimer, bloc « Lectures : x sur y » avec barre |
| Modale | Titre, catégorie, message (15 caractères minimum), « Épingler en haut de la liste » |

## Règles

- Publier notifie tous les salariés en poste (e-mail pour les annonces épinglées, M-16).
- Supprimer : confirmation destructive, annulable depuis la notification visuelle.
- Texte simple avec retours à la ligne et liens détectés automatiquement ; pas de HTML libre (sécurité).
- Lot 8 : ciblage par service ou site, pièces jointes, relance des non-lecteurs.

## Critères d'acceptation

- Ouvrir une annonce la marque comme lue pour cette seule personne et met à jour le compteur.
- Un salarié ne voit aucun bouton de gestion et reçoit 403 sur les URL de modification.
- Un message contenant `<script>` est affiché comme du texte.
