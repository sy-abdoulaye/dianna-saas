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
- Moins de 5 réponses : « Résultats masqués » (seuil d'anonymat, M-10, porté à 5 : L6-17). Les commentaires suivent la même règle.
- Résultats visibles seulement après la clôture ou l'échéance passée (L6-01). Pendant l'ouverture : « N réponses reçues · Les résultats seront visibles à la clôture ». Jamais de liste des répondants ni des non-répondants, pour aucun profil.
- Commentaires à note égale : dans un ordre qui ne suit pas celui des réponses (clé aléatoire).
- 5 commentaires par question, puis « Afficher plus » par paquets de 20 (L6-22).
- Lot 8 : résultats par service seulement si le service compte au moins le seuil de répondants.

## Cycle de vie

Brouillon → (Publier, confirmation, notification au public) → Ouvert → (Clore, confirmation, ou automatiquement le lendemain de l'échéance) → Clos. Un brouillon peut être modifié (« Modifier le brouillon », L6-07) ou supprimé ; un questionnaire publié n'est plus modifiable. Le public est figé à la publication ; un public de moins de 5 personnes ne peut pas être publié (L6-05, L6-17). Un questionnaire ouvert peut voir son échéance prolongée vers une date à venir, tant que l'échéance n'est pas passée (« Prolonger l'échéance », L6-21). Après l'échéance, il est clos partout (statut affiché, réponses refusées, résultats selon le seuil), même avant sa clôture automatique, et ne peut plus être prolongé : « L'échéance est passée : le questionnaire ne peut plus être prolongé. ». Une confirmation ne s'ouvre que si l'action est possible ; sinon le message dit l'état réel (L6-20).

## Limite connue (L1-09)

L'anonymat est garanti au niveau de l'application. En base, par un accès SQL direct, l'ordre physique des lignes et le numéro de transaction (`xmin` du reçu = `xmin` de la réponse + 1, le reçu étant écrit dans une sous-transaction) peuvent permettre de les rapprocher quand les réponses sont peu nombreuses ; une sauvegarde (`pg_dump`) garde l'ordre physique, donc ce lien. Les réponses ne portent plus de date (L6-02). Risque résiduel accepté pour la V1, à revoir au lot 8 (réécriture groupée des réponses, aucun accès SQL direct hors procédure tracée).

## Critères d'acceptation

- Aucune requête ni aucun export ne permet de relier une réponse à une personne (pas de clé commune entre `SurveyReceipt` et `SurveyResponse`).
- Répondre deux fois est impossible, même en renvoyant le formulaire.
- Un commentaire saisi apparaît dans les résultats sous sa question, avec sa note.
- Avec 4 réponses, les résultats et commentaires sont masqués (seuil de 5).
- Un salarié n'accède pas aux résultats (403).
