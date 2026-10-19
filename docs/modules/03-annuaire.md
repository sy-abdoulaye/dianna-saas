# Annuaire

## Écrans

| Route | Écran |
|---|---|
| `/annuaire/` | Liste ou cartes. Sous-titre : nombre de collaborateurs, de sites, de services. Bandeau d'information pour Salarié et Manager (« Les informations RH ne sont pas affichées »). Action RH/Admin : « Ajouter un collaborateur » |
| `/annuaire/<id>/` | Fiche : en-tête (avatar, statut, manager, « C'est vous »), onglets Informations, Équipe, Demandes (soi, manager, RH), Historique (RH) |
| `/annuaire/nouveau/`, `/annuaire/<id>/modifier/` | Formulaire en page complète : Identité et contact (avec photo), Poste et organisation, Informations RH, Accès à Dianna (Admin : profil d'accès, invitation) ; bloc « Enregistrer » collant à droite |
| `/annuaire/import/` | Admin : import CSV en 3 temps (fichier, aperçu avec erreurs ligne par ligne, confirmation) |

**Barre de filtres :** recherche (nom, poste, service, e-mail), service, site, statut (RH : En poste, Partis, Tous), Réinitialiser, sélecteur Liste/Cartes (mémorisé). Pagination : 8 en liste, 12 en cartes.

**Tableau :** Collaborateur (avatar, nom cliquable, poste), Service, Site, Manager, E-mail ; RH : Statut et actions (Modifier, Archiver ou Réactiver).

**Fiche, onglet Informations :** Coordonnées professionnelles, Organisation, Informations RH (RH : « Réservé aux RH » ; la personne elle-même : « Visible par vous et les RH »), bloc Contacter avec boutons « Copier », Raccourcis (fiche de suivi, demandes).

## Règles

- E-mail obligatoire, valide, unique dans l'entreprise. Message : « Cette adresse est déjà utilisée par {nom}. »
- L'e-mail de la fiche est le contact professionnel ; l'identifiant de connexion (`User.email`) est créé avec cette adresse à l'invitation, puis ne change plus quand la fiche change. Changer d'identifiant est une action séparée, confirmée par e-mail (T-09). Inviter une adresse déjà utilisée dans une autre entreprise est refusé : « Cette adresse est déjà utilisée sur Dianna. Utilisez une autre adresse ou contactez le support. »
- « Arrivée prochaine » : visible de tous avec son badge, comptée dans le filtre « En poste » (L1-04).
- Manager : toute fiche active peut être choisie (L1-02).
- Champs obligatoires : prénom, nom, e-mail, poste, service, site, date d'arrivée.
- Date d'arrivée future : statut « Arrivée prochaine ».
- Photo : JPG ou PNG, 2 Mo maximum ; sans photo, initiales.
- Archiver : confirmation, statut « Parti », date de départ = aujourd'hui (modifiable), la personne disparaît de l'annuaire salarié, son compte est désactivé, ses données sont conservées. Annulable depuis la notification visuelle. Réactiver : statut « Actif ».
- Un salarié ou un manager modifie seulement son téléphone et son bureau (modale « Modifier mes coordonnées »).
- Chaque modification crée un `EmployeeChange` et une ligne du journal d'audit.
- Import CSV : colonnes `prenom;nom;email;poste;service;site;manager_email;date_arrivee;contrat`. Services et sites inconnus créés après confirmation. Aucune ligne importée si une erreur bloquante reste.

## Critères d'acceptation

- Un salarié ne voit ni la colonne Statut, ni les fiches parties, ni les informations RH d'un collègue (vérifié dans le HTML rendu, pas seulement visuellement).
- Un manager voit les coordonnées de son équipe mais pas ses informations RH (V-07).
- La recherche « zzzz » affiche l'état vide « Aucun collaborateur trouvé » avec « Réinitialiser les filtres ».
- Créer une fiche avec une adresse existante affiche l'erreur sous le champ et le résumé d'erreurs, sans perdre la saisie.
- L'archivage puis « Annuler » dans la notification rétablit le statut « Actif ».
- Les filtres et la page sont dans l'URL (lien partageable, bouton Retour du navigateur fonctionnel).
