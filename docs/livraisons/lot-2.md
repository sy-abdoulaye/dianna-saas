# Note de livraison : lot 2, annuaire et administration

Date : 19 octobre 2026. Branche : `lot-2`.

## Ce qui est fait

**Annuaire (`docs/modules/03-annuaire.md`).**
- Liste et cartes, recherche, filtres service, site et statut (RH : En poste, Partis, Tous), pagination 8 ou 12, filtres et page dans l'URL, sélecteur mémorisé.
- Bandeau « Les informations RH ne sont pas affichées » pour les salariés et managers.
- Fiche à onglets : Informations, Équipe, Historique (RH). Les informations RH ne sont visibles que de la personne et des RH (V-07). Bouton « Copier ».
- Création et modification en page complète : photo (JPG ou PNG, 2 Mo), profil d'accès et invitation réservés à l'administrateur, contrôle de l'adresse dans l'entreprise, des boucles de hiérarchie et du matricule.
- Archivage avec confirmation et date de départ, compte désactivé, annulation pendant 30 s ; réactivation ; « Modifier mes coordonnées ».
- Historique de la fiche (noms des champs seulement) et journal d'audit à chaque modification.
- Import CSV en 3 temps (fichier, aperçu ligne par ligne, confirmation tout ou rien), services et sites inconnus créés à la confirmation.
- Recherche globale dans la barre du haut (5 suggestions, Entrée ouvre l'annuaire filtré) et « Ma fiche ».

**Administration (`docs/modules/04-administration.md`).**
- Entreprise : nom, quota de télétravail (0 à 5), validation automatique du télétravail (M-02), validation finale RH des congés d'été (M-03), logo affiché à la connexion.
- Utilisateurs et profils : recherche, filtre, changement de profil avec confirmation (pas le sien, jamais le dernier administrateur), état du compte, envoi et renvoi d'invitation.
- Services et sites : ajout, renommage, suppression ; « Suppression impossible » avec le nombre de collaborateurs et le lien vers l'annuaire filtré.
- Modules : activation immédiate, désactivation confirmée ; annuaire toujours activé ; Plan de charge et Recrutement « Non disponible ».
- Journal d'activité : recherche, période, export CSV journalisé.

**Tableau de bord, version initiale.** Indicateurs Administrateur et RH déjà calculables, « À traiter » (Tout est à jour), raccourci Annuaire, bouton Administration pour l'administrateur.

**Socle.** Fichiers privés servis par URL signée de 5 minutes liée à l'entreprise ; `TenantManager` constructible à l'import mais illisible sans entreprise (L2-12).

## Tests

| Commande | Résultat |
|---|---|
| `make lint` | sans erreur |
| `make test` | 279 tests ; couverture 95 % au total, de 90 à 99 % sur chaque `services.py`, `permissions.py` et l'import |
| `make e2e` | 30 parcours, dont le parcours 4 (RH) et le parcours 5 (Administrateur) |
| `make check` | aucune alerte, dont `--deploy` |

## Critères d'acceptation

| Fiche | Critère | État |
|---|---|---|
| Annuaire | Salarié : ni colonne Statut, ni fiches parties, ni informations RH d'un collègue, dans le HTML | Fait |
| Annuaire | Manager : coordonnées de son équipe sans informations RH | Fait |
| Annuaire | « zzzz » : état vide et « Réinitialiser les filtres » | Fait |
| Annuaire | Adresse existante : erreur sous le champ et résumé, saisie conservée | Fait |
| Annuaire | Archivage puis « Annuler » : statut « Actif » | Fait |
| Annuaire | Filtres et page dans l'URL, bouton Retour | Fait |
| Administration | Désactiver Télétravail : entrée retirée du menu, données conservées | Fait. La page « Module désactivé » sur ses URL arrive avec l'écran Télétravail (lot 3) |
| Administration | Supprimer un service utilisé : « Suppression impossible » | Fait |
| Administration | Rétrograder le dernier administrateur : refus explicite | Fait |
| Administration | Toutes les actions de l'onglet au journal | Fait |
| Socle | Salarié sur `/administration/` : « Accès non autorisé » | Fait |
| Tableau de bord | Modules désactivés absents des blocs | Fait (aucun bloc de module encore) |

## Écarts et points à relire

- Décisions L2-01 à L2-11 dans `00-decisions.md`, statut « À confirmer » ; dépendance ajoutée : Pillow 12.3.
- Changement d'identifiant de connexion (T-09) : non livré, à planifier (L2-11).
- Écarts au prototype : fiche partie en 404 (L2-03) ; onglet Entreprise selon la fiche (L2-08) ; photo et logo par la zone de fichier du design system.
