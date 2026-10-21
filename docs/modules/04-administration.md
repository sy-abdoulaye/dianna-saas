# Administration

Route : `/administration/`, profil Administrateur uniquement. Onglets :

| Onglet | Contenu |
|---|---|
| Entreprise | Nom, jours de télétravail par semaine (0 à 5), validation automatique du télétravail (M-02), validation finale RH des congés d'été (M-03), logo. Les campagnes de congés se gèrent dans le module Congés (RH) |
| Compétences (lot 7) | Liste ordonnée des compétences évaluées en entretien individuel : ajouter, renommer, réordonner, désactiver |
| Utilisateurs et profils | Recherche, filtre par profil, tableau Utilisateur / E-mail / Profil d'accès (liste déroulante, confirmation à chaque changement ; son propre profil n'est pas modifiable), bouton « Inviter un utilisateur » (ouvre la création de fiche), renvoi d'invitation |
| Services et sites | Deux listes avec nombre de collaborateurs, Ajouter, Renommer, Supprimer. Un site se « Modifie » : nom et case « Jours fériés d'Alsace-Moselle » (L4-02) |
| Fermetures (lot 4) | Fermetures à venir (date, libellé, périmètre : toute l'entreprise ou un site) avec les demandes de télétravail concernées, et fermetures des 12 derniers mois ; « Ajouter une fermeture » et « Supprimer » pour l'administrateur. Les RH voient cet onglet seul, en lecture (L4-04). Les jours fériés sont pris en compte sans saisie |
| Modules | Interrupteur par module avec description ; Plan de charge et Recrutement « Non disponible ». L'annuaire fait partie du socle et n'est pas désactivable (L1-05) |
| Journal d'activité | Recherche, liste horodatée (qui, quoi), export CSV de la période |

## Règles

- Supprimer un service ou un site encore utilisé est impossible : modale « Suppression impossible » indiquant le nombre de collaborateurs, avec lien vers l'annuaire.
- Noms de service et de site uniques dans l'entreprise (insensible à la casse).
- Désactiver un module : confirmation (« Le module disparaîtra du menu de tous les utilisateurs. Les données sont conservées »). Activer : immédiat.
- Changer un profil : confirmation, effet à la requête suivante de la personne, journalisé.
- Il doit toujours rester au moins un Administrateur actif.
- Fermeture : date passée refusée (« La date est passée. ») ; une seule par jour et par périmètre (« Une fermeture existe déjà ce jour-là pour ce périmètre. »). Les demandes de télétravail déjà faites ce jour-là restent en place ; les RH reçoivent une notification avec leur liste (L4-03). Ajout et suppression sont journalisés.

## Critères d'acceptation

- Désactiver Télétravail retire l'entrée du menu pour tous et affiche « Module désactivé » sur ses URL ; les demandes existantes restent en base.
- Supprimer « Finance » (utilisé) affiche « Suppression impossible ».
- Rétrograder le dernier Administrateur est refusé avec un message explicite.
- Toutes les actions de l'onglet apparaissent dans le journal.
