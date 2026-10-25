# Tableau de bord

Route : `/`. Titre « Bonjour {prénom} », sous-titre : date, profil, entreprise. Action principale : « Déclarer du télétravail » (Admin : « Administration »).

## Contenu par profil

| Bloc | Salarié | Manager | RH | Admin |
|---|---|---|---|---|
| Indicateurs (4) | Télétravail cette semaine (x / quota), mes demandes en attente, matériel attribué, annonces non lues | Demandes à valider, équipe sur site aujourd'hui, entretiens à mener, télétravail aujourd'hui | Justificatifs à valider, avancement de la campagne d'entretiens, effectif en poste, arrivées à venir | Utilisateurs actifs, modules activés, services, événements du journal |
| À traiter | Ses entretiens à compléter, questionnaires à remplir, comptes rendus à envoyer ou compléter | + demandes à valider par module, comptes rendus à valider, entretiens à mener | + validations RH | idem RH |
| Aujourd'hui | Répartition sur site, télétravail, congés, astreinte de son service | idem | toute l'entreprise | toute l'entreprise |
| Mes dernières demandes | 4 dernières | idem | idem | — |
| Annonces | 3 plus récentes (épinglées d'abord), pastille « Nouveau » si non lue | idem | idem | idem |
| Raccourcis | Annuaire, Carrière, Mon matériel | idem | idem | idem |

État vide « Tout est à jour » quand il n'y a rien à traiter.

**Lot 4 (L4-08).** Les blocs et indicateurs des modules à venir (matériel, annonces, justificatifs, entretiens, questionnaires, comptes rendus) restent masqués jusqu'à leur lot. Indicateurs affichés :
- Salarié : Télétravail cette semaine, Mes demandes en attente, Mes prochains congés, Sur site aujourd'hui (son service).
- Manager : Demandes à valider, Équipe sur site aujourd'hui, En télétravail aujourd'hui, En congés aujourd'hui.
- RH : Demandes à valider, Vœux de la campagne (si une campagne est ouverte), Effectif en poste, Arrivées à venir.
- Admin : inchangé.
« À traiter » : une ligne par module avec des demandes à valider (mêmes compteurs que le menu), bouton « Ouvrir » vers l'onglet « À valider ». « Aujourd'hui » : répartition du périmètre du planning, lien « Voir le planning ». Raccourcis : Annuaire.

**Lot 7.** « À traiter » ajoute les entretiens à compléter (lien vers « À faire par moi ») et les comptes rendus à valider ou à envoyer ; indicateurs « Entretiens à mener » (manager, à la place de « En congés aujourd'hui ») et « Campagne d'entretiens » (RH, si une campagne est en cours) ; raccourci « Carrière ».

## Critères d'acceptation

- Chaque élément « À traiter » mène à l'écran où l'action se fait.
- Les compteurs du tableau de bord et du menu sont identiques.
- Les modules désactivés n'apparaissent dans aucun bloc.
