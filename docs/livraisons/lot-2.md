# Note de livraison : lot 2, annuaire et administration

Date : 19 octobre 2026, corrections de l'audit le 20 octobre 2026. Branche : `lot-2`.

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

**Socle.** Fichiers privés servis par URL signée de 5 minutes liée à l'entreprise ; querysets métier liés à l'entreprise de leur construction (L2-12, A2-01).

## Corrections de l'audit du lot 2 (A2-01 à A2-07)

- **Isolation :** un queryset métier mémorise l'entreprise de sa construction ; évalué sans entreprise, dans une autre entreprise ou après avoir été construit sans entreprise, il lève une erreur au lieu de renvoyer une liste vide ou les données d'une autre entreprise. Règle ajoutée à CLAUDE.md : pas de queryset métier au niveau d'une classe.
- **Images :** 40 millions de pixels au plus, vérifiés avant décodage (« Image trop grande. ») ; image reconstruite à partir de ses seuls pixels : plus aucune métadonnée, commentaire JPEG compris.
- **Exports CSV :** fonction commune qui neutralise les formules (=, +, -, @, tabulation, retour chariot) ; règle ajoutée à CLAUDE.md.
- **Profil d'accès :** tout changement passe par `change_role` (journal `people.role_changed`) ; son propre profil n'est ni affiché ni modifiable depuis sa fiche.
- **Photo à la création :** rangée dans le dossier de l'entreprise et affichée sur la fiche.
- **Archivage :** seul un administrateur archive un administrateur.
- **Import CSV :** fichiers malformés et longueurs trop grandes signalés avec le numéro de ligne ; confirmation expirée renvoyée à l'étape 1.

## Tests

| Commande | Résultat |
|---|---|
| `make lint` | sans erreur |
| `make test` | 338 tests ; couverture 95 % au total, de 92 à 99 % sur chaque `services.py`, `permissions.py` et l'import |
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

- Décisions L2-01 à L2-11 dans `00-decisions.md`, statut « À confirmer » ; décisions de l'audit A2-01 à A2-07 ; dépendance ajoutée : Pillow 12.3.
- Changement d'identifiant de connexion (T-09) : non livré, prévu au lot 8 (L2-11, « Pour plus tard »).
- Écarts au prototype : fiche partie en 404 (L2-03) ; onglet Entreprise selon la fiche (L2-08) ; photo et logo par la zone de fichier du design system.
