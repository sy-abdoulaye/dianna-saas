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
- Résultats visibles seulement après la clôture ou l'échéance passée (L6-01). Pendant l'ouverture : « N réponses reçues · Les résultats seront visibles à la clôture ». Jamais de liste des répondants ni des non-répondants, pour aucun profil.
- Commentaires à note égale : dans un ordre qui ne suit pas celui des réponses (clé aléatoire).
- Lot 8 : résultats par service seulement si le service compte au moins le seuil de répondants.

## Cycle de vie

Brouillon → (Publier, confirmation, notification au public) → Ouvert → (Clore, confirmation, ou automatiquement le lendemain de l'échéance) → Clos. Un brouillon peut être modifié (« Modifier le brouillon », L6-07) ou supprimé ; un questionnaire publié n'est plus modifiable. Le public est figé à la publication ; un public de moins de 3 personnes ne peut pas être publié (L6-05).

## Limite connue (L1-09)

L'anonymat est garanti au niveau de l'application. En base, par un accès SQL direct, l'ordre physique des lignes et le numéro de transaction (`xmin`, commun au reçu et à la réponse) peuvent permettre de les rapprocher quand les réponses sont peu nombreuses. Les réponses ne portent plus de date (L6-02). Risque résiduel accepté pour la V1, à revoir au lot 8 (réécriture groupée des réponses, aucun accès SQL direct hors procédure tracée).

## Critères d'acceptation

- Aucune requête ni aucun export ne permet de relier une réponse à une personne (pas de clé commune entre `SurveyReceipt` et `SurveyResponse`).
- Répondre deux fois est impossible, même en renvoyant le formulaire.
- Un commentaire saisi apparaît dans les résultats sous sa question, avec sa note.
- Avec 2 réponses, les résultats et commentaires sont masqués.
- Un salarié n'accède pas aux résultats (403).
