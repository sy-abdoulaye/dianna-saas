# Carrière et évaluations

## Écrans

| Route | Écran |
|---|---|
| `/carriere/` | Titre, sous-titre de campagne (« Campagne 2026 · du 5 octobre au 18 décembre »). Actions : « Lancer un entretien » (Manager, RH) ; « Ma fiche de suivi » (Salarié). Indicateurs : campagne terminée (%), à faire par vous, entretiens planifiés. Onglets Entretiens / Fiches de suivi (Manager, RH). Filtres : recherche, type, avancement (À faire par moi, En cours, Clos). Tableau : collaborateur, type, avancement (4 segments), statut (« À faire par vous », étape en cours, « Clos »), date d'entretien, action (Compléter / Ouvrir) |
| `/carriere/<id>/` | Entretien : étapes en haut ; à gauche, l'étape en cours (formulaire si la personne doit agir, sinon « En attente de {nom} » avec « Relancer » pour Manager et RH), puis les parties déjà remplies en lecture ; à droite, Entretien (date, manager, campagne), Signatures, mention de confidentialité, lien vers la fiche de suivi |
| `/carriere/fiche/<employee_id>/` | Fiche de suivi : historique (date, auteur, type, « Privée »), synthèse (manager, dernier entretien), formations ; actions « Ajouter une note », « Exporter en PDF » |
| Modale « Lancer un entretien » | Collaborateur (périmètre du profil), type, motif (entretien de parcours : périodique, retour d'absence, mi-carrière, fin de carrière, état des lieux). Refus si un entretien du même type est déjà en cours pour la personne |
| Modale « Campagne d'entretiens » (RH) | Libellé, début, fin ; deux campagnes ne se chevauchent pas (L7-04) |
| Modale « Ajouter une note » | Type (Point de suivi, Souhait salarié, Formation, Entretien ; le salarié : Souhait seulement), note (8 caractères minimum), « Note privée » (manager) |

## Déroulé

| Étape | Entretien individuel | Entretien de parcours professionnel | Qui agit |
|---|---|---|---|
| 1 | Auto-évaluation : bilan de l'année (20 caractères minimum) | Préparation : parcours, projet professionnel et souhaits | Salarié |
| 2 | Évaluation du manager : bilan ; 4 compétences notées de 1 à 4 (1 à développer · 2 correct · 3 maîtrisé · 4 référent) ; points forts ; axes de progrès ; objectifs de l'année suivante (1 obligatoire, 2 ou plus facultatifs) avec échéance | Entretien : planifier, puis marquer comme réalisé | Manager |
| 3 | Entretien : date (pas dans le passé) et lieu ; « Marquer l'entretien comme réalisé » (confirmation) | Compte rendu ; formations retenues (une par ligne) ; échéances suggérées ; état des lieux à 8 ans au motif « état des lieux » | Manager |
| 4 | Signatures du salarié et du manager | idem | Les deux |
| Fin | Clos : une note est ajoutée à la fiche de suivi | idem | — |

- Chaque étape notifie la personne suivante. « Relancer » renvoie une notification.
- La signature confirme la tenue de l'entretien, pas l'accord du salarié ; le salarié peut ajouter un commentaire avant de signer (lot 7).
- Un RH peut agir à la place d'un manager absent (bandeau d'avertissement, journalisé). Si la personne n'a pas de manager, les RH tiennent ce rôle.
- « Marquer l'entretien comme réalisé » n'est possible qu'à partir de la date planifiée.
- Ordre des étapes : individuel = auto-évaluation → évaluation du manager → entretien → signatures ; parcours professionnel = préparation → entretien → compte rendu → signatures.
- Entretien de parcours professionnel : bloc « État des lieux à 8 ans » au motif « état des lieux », avec les 3 critères (au moins une action de formation, une certification, une progression salariale ou professionnelle), chacun oui, non ou non renseigné (L7-03).
- Compétences paramétrables par l'entreprise (administration, onglet « Compétences », L7-16).

## Règles légales de l'entretien de parcours (M-08, à confirmer par un juriste)

Sources : loi n° 2025-989 du 24 octobre 2025, article L6315-1 du Code du travail modifié ; questions-réponses du ministère du Travail mis à jour en février 2026.

- L'« entretien professionnel » devient l'« entretien de parcours professionnel » (libellé de l'application, écart au prototype).
- Premier entretien dans la première année de présence, puis tous les 4 ans au plus (un accord d'entreprise ou de branche peut prévoir plus court). Le délai court depuis le dernier entretien réalisé ; les accords prévoyant plus de 4 ans ne s'appliquent plus après le 1er octobre 2026.
- État des lieux récapitulatif tous les 8 ans, avec les 3 critères ; l'abondement CPF est apprécié sur 8 ans dans les entreprises d'au moins 50 salariés. Dianna ne calcule pas l'abondement.
- Entretien de mi-carrière (dans les 2 mois suivant la visite médicale de l'année des 45 ans) et de fin de carrière (dans les 2 ans précédant 60 ans) : aucune date de naissance n'est stockée, le RH les lance avec le motif correspondant.
- Réglages de l'entreprise (onglet Entreprise) : périodicité de l'entretien (4 ans par défaut, 4 au plus) et de l'état des lieux (8 ans). Échéances suggérées, modifiables : première année depuis l'arrivée, puis la périodicité après le dernier entretien de parcours réalisé ; état des lieux 8 ans après l'arrivée, puis après le dernier état des lieux (L7-02).
- **À confirmer par un juriste** : absences qui ouvrent droit à l'entretien de retour, délais de mi-carrière et de fin de carrière, contenu attendu de l'état des lieux, remise d'une copie écrite au salarié, appréciation de l'abondement, durées de conservation (M-13).

## Critères d'acceptation

- Un salarié ne voit que ses propres entretiens ; ouvrir celui d'un collègue renvoie 404.
- Un manager ne peut pas remplir l'auto-évaluation de son collaborateur.
- L'évaluation est bloquée tant que les 4 compétences ne sont pas notées.
- L'entretien n'est clos qu'avec les deux signatures ; une note est alors ajoutée à la fiche de suivi.
- Une note privée du manager n'est visible ni par le salarié, ni par les RH.
- Lancer un entretien puis « Annuler » dans la notification supprime l'entretien et sa notification.
