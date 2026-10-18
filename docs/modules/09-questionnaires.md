# Questionnaires

| Route | Écran |
|---|---|
| `/questionnaires/` | Bandeau « N questionnaires à remplir » avec liens. Filtres : recherche, statut (Ouverts, Clos ; RH : Brouillons). Tableau : titre, public, nombre de questions, statut, réponses (x sur y avec barre ; « — » pour un brouillon), échéance, action (Répondre / Voir / Ouvrir) |
| `/questionnaires/<id>/` | Selon le cas : formulaire de réponse ; résultats ; aperçu du brouillon (RH) ; message « Merci, votre réponse est enregistrée » ou « Ce questionnaire est clos ». Manager et RH qui n'ont pas répondu : sélecteur « Répondre / Résultats » |
| Modale de création (RH) | Titre, public (Tous les salariés, Managers, Arrivés depuis moins d'un an), échéance, questions notées de 1 à 5 (une par ligne), question ouverte facultative. Crée un brouillon |

## Réponse

- Bandeau : « Vos réponses sont anonymes : les résultats ne montrent jamais qui a répondu quoi. »
- Question notée : note de 1 à 5 obligatoire (« 1 = pas du tout d'accord · 5 = tout à fait d'accord »), puis **« Commentaire (facultatif) »** pour justifier la note (V-09).
- Question ouverte : texte facultatif.
- Une seule réponse par personne (reçu séparé, M-10).

## Résultats (Manager, RH, Admin)

- Indicateurs : réponses, participation (%), échéance.
- Par question notée : moyenne sur 5, répartition 5 à 1 en barres, puis **« Commentaires (n) »** : chaque commentaire avec sa note, sans nom, triés de la note la plus haute à la plus basse.
- Par question ouverte : liste des réponses.
- Moins de 3 réponses : « Résultats masqués » (seuil d'anonymat, M-10). Les commentaires suivent la même règle.
- Lot 8 : résultats par service seulement si le service compte au moins le seuil de répondants.

## Cycle de vie

Brouillon → (Publier, confirmation, notification au public) → Ouvert → (Clore, confirmation) → Clos. Un brouillon peut être supprimé ; un questionnaire publié n'est plus modifiable.

## Limite connue (L1-09)

L'anonymat est garanti au niveau de l'application. En base, l'ordre physique des lignes et la date du jour peuvent permettre de rapprocher un reçu et une réponse quand les réponses sont peu nombreuses. Risque résiduel accepté pour la V1, à revoir au lot 8.

## Critères d'acceptation

- Aucune requête ni aucun export ne permet de relier une réponse à une personne (pas de clé commune entre `SurveyReceipt` et `SurveyResponse`).
- Répondre deux fois est impossible, même en renvoyant le formulaire.
- Un commentaire saisi apparaît dans les résultats sous sa question, avec sa note.
- Avec 2 réponses, les résultats et commentaires sont masqués.
- Un salarié n'accède pas aux résultats (403).
