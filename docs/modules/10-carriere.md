# Carrière et évaluations

## Écrans

| Route | Écran |
|---|---|
| `/carriere/` | Titre, sous-titre de campagne (« Campagne 2026 · du 5 octobre au 18 décembre »). Actions : « Lancer un entretien » (Manager, RH) ; « Ma fiche de suivi » (Salarié). Indicateurs : campagne terminée (%), à faire par vous, entretiens planifiés. Onglets Entretiens / Fiches de suivi (Manager, RH). Filtres : recherche, type, avancement (À faire par moi, En cours, Clos). Tableau : collaborateur, type, avancement (4 segments), statut (« À faire par vous », étape en cours, « Clos »), date d'entretien, action (Compléter / Ouvrir) |
| `/carriere/<id>/` | Entretien : étapes en haut ; à gauche, l'étape en cours (formulaire si la personne doit agir, sinon « En attente de {nom} » avec « Relancer » pour Manager et RH), puis les parties déjà remplies en lecture ; à droite, Entretien (date, manager, campagne), Signatures, mention de confidentialité, lien vers la fiche de suivi |
| `/carriere/fiche/<employee_id>/` | Fiche de suivi : historique (date, auteur, type, « Privée »), synthèse (manager, dernier entretien), formations ; actions « Ajouter une note », « Exporter en PDF » |
| Modale « Lancer un entretien » | Collaborateur (périmètre du profil), type. Refus si un entretien du même type est déjà en cours pour la personne |
| Modale « Ajouter une note » | Type (Point de suivi, Souhait salarié, Formation, Entretien ; le salarié : Souhait seulement), note (8 caractères minimum), « Note privée » (manager) |

## Déroulé

| Étape | Entretien individuel | Entretien professionnel | Qui agit |
|---|---|---|---|
| 1 | Auto-évaluation : bilan de l'année (20 caractères minimum) | Préparation : parcours, projet professionnel et souhaits | Salarié |
| 2 | Évaluation du manager : bilan ; 4 compétences notées de 1 à 4 (1 à développer · 2 correct · 3 maîtrisé · 4 référent) ; points forts ; axes de progrès ; objectifs de l'année suivante (1 obligatoire, 2 ou plus facultatifs) avec échéance | Entretien : planifier, puis marquer comme réalisé | Manager |
| 3 | Entretien : date (pas dans le passé) et lieu ; « Marquer l'entretien comme réalisé » (confirmation) | Compte rendu ; formations retenues (une par ligne) | Manager |
| 4 | Signatures du salarié et du manager | idem | Les deux |
| Fin | Clos : une note est ajoutée à la fiche de suivi | idem | — |

- Chaque étape notifie la personne suivante. « Relancer » renvoie une notification.
- La signature confirme la tenue de l'entretien, pas l'accord du salarié ; le salarié peut ajouter un commentaire avant de signer (lot 7).
- Un RH peut agir à la place d'un manager absent (bandeau d'avertissement, journalisé). Si la personne n'a pas de manager, les RH tiennent ce rôle.
- « Marquer l'entretien comme réalisé » n'est possible qu'à partir de la date planifiée.
- Ordre des étapes : individuel = auto-évaluation → évaluation du manager → entretien → signatures ; professionnel = préparation → entretien → compte rendu → signatures.
- Entretien professionnel : bloc « Bilan à 6 ans » avec les 3 critères (action de formation, élément de certification, progression) et l'échéance. Règles légales à valider (M-08).
- Compétences paramétrables par l'entreprise (lot 7, écran d'administration).

## Critères d'acceptation

- Un salarié ne voit que ses propres entretiens ; ouvrir celui d'un collègue renvoie 404.
- Un manager ne peut pas remplir l'auto-évaluation de son collaborateur.
- L'évaluation est bloquée tant que les 4 compétences ne sont pas notées.
- L'entretien n'est clos qu'avec les deux signatures ; une note est alors ajoutée à la fiche de suivi.
- Une note privée du manager n'est visible ni par le salarié, ni par les RH.
- Lancer un entretien puis « Annuler » dans la notification supprime l'entretien et sa notification.
