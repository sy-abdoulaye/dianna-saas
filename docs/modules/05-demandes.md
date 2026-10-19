# Demandes : télétravail, congés estivaux, astreintes, transport

Les quatre modules partagent le moteur de validation (`02-architecture.md`) et le même gabarit d'écran.

## Gabarit commun

| Route | Écran |
|---|---|
| `/<module>/` | En-tête (titre, sous-titre, actions « Voir le planning » et « Nouvelle demande »), bloc propre au module, onglets **Mes demandes** / **À valider** (avec compteur, si la personne est valideuse) / **Mon équipe** (manager) ou **Toutes les demandes** (RH), barre de filtres (recherche, statut), tableau, pagination (8) |
| Modale de création | Icône du module, champs, encadré d'aide, boutons « Annuler » et « Envoyer la demande » de même largeur |
| Modale de détail | Demandeur, statut, alerte de conflit éventuelle, champs, historique ; actions selon le profil (Valider, Refuser, Annuler la demande, Fermer) |
| Modale de refus | Motif obligatoire, transmis au demandeur |

**Tableau :** Collaborateur (sauf « Mes demandes »), détail de la demande, date d'envoi, statut, actions : Valider et Refuser (valideur), Annuler (demandeur, en attente), Détail.

**États vides :** « Rien à valider » (onglet À valider) ; « Aucune demande ne correspond » (filtres) ; « Aucune demande pour le moment » avec bouton de création (Mes demandes).

**Valideur (L1-02, M-12) :** le manager direct du demandeur, quel que soit son profil. Sans manager : les RH et administrateurs autres que le demandeur ; s'il n'y en a aucun, la demande est validée automatiquement et le journal note « validation automatique : aucun valideur disponible ».

**Annulation après envoi (L1-08) :** la demande est supprimée ; le journal d'audit garde « demande envoyée puis retirée ».

**Transitions :** voir `02-architecture.md`. Après envoi, validation ou refus : notification visuelle avec « Annuler » (30 s, L0-03), notification au destinataire, e-mail selon M-16, journal d'audit.

## Télétravail

- **Bloc :** indicateurs « Cette semaine x / quota », « En attente de validation », « Règle de l'entreprise : N jours par semaine ».
- **Champs :** Jour (obligatoire), Commentaire (facultatif).
- **Contrôles :** jour ouvré (« Le télétravail se déclare du lundi au vendredi. ») ; pas dans le passé ; pas de doublon le même jour ; quota hebdomadaire (demandes en attente + validées) : « Vous avez déjà {n} jours de télétravail la semaine du {date} (maximum {quota}). » ; quota individuel si dérogation.
- **Validation :** manager direct ; automatique si l'entreprise l'a choisi (M-02).
- **Export (RH, lot 4) :** récapitulatif mensuel des jours de télétravail validés par salarié (CSV, Excel).
- **Planning :** événement « Télétravail » (hachuré tant qu'il est en attente).

## Congés estivaux

- **Bloc :** bandeau de campagne « Campagne Été 2027 : déposez vos vœux avant le {date limite} », lien vers le planning.
- **Champs :** Premier jour, Dernier jour (côte à côte), Type (Congés d'été, Autre absence), Commentaire.
- **Contrôles :** dates non passées ; fin ≥ début ; 31 jours au plus ; pas de chevauchement avec ses propres demandes actives ; pendant la campagne, dates comprises dans la période de la campagne pour le type « Congés d'été ».
- **Conflit :** si d'autres personnes du même service ont une absence (en attente ou validée) sur la période, l'afficher (nombre et noms) dans le tableau du valideur et dans le détail ; alerte renforcée au-delà du seuil de la campagne (M-03). L'envoi n'est pas bloqué.
- **Validation (M-03) :** le manager arbitre (Valider → statut « Validée par le manager », ou Refuser) ; si `Company.summer_leave_hr_step` est actif, la demande apparaît ensuite dans « À valider » des RH, qui valident ou refusent. Sans étape RH, la validation du manager est finale. « Autre absence » : manager seul.
- **Campagnes (RH), écran `/conges/campagnes/` :** créer (libellé, période, date limite, seuil de conflit en %), ouvrir, clore ; une seule campagne ouverte à la fois. Après la clôture, les nouvelles demandes d'été passent par le type « Autre absence ».
- **Synthèse par service (RH, lot 4) :** pour la campagne, nombre de vœux, absents par semaine et par service, alertes de dépassement du seuil.

## Astreintes

- **Champs :** Type (Astreinte, Intervention), Début et Fin (côte à côte), Durée d'intervention en heures (pas de 0,5 ; obligatoire pour une intervention), Description.
- **Contrôles :** fin ≥ début ; durée > 0 et ≤ 24 pour une intervention. Début et fin sont des **dates incluses** (pas d'heures en V1).
- **Planning :** une astreinte crée un événement « Astreinte » (hachuré tant qu'elle est en attente) ; une intervention n'est pas projetée au planning, elle sert à l'export paie.
- **Export paie (RH) :** récapitulatif mensuel des astreintes et interventions validées par salarié (CSV et Excel).

## Justificatifs de transport

- **Bloc :** information sur le remboursement estimé (50 % de l'abonnement, M-06), précisant que le remboursement n'est pas géré par Dianna.
- **Champs :** Mois concerné, Type de titre (Abonnement mensuel, Abonnement annuel, Titre unique), Montant payé (€), Justificatif (zone de fichier : PDF, JPG ou PNG, 5 Mo).
- **Validité :** un abonnement mensuel ou un titre unique couvre le mois choisi ; un abonnement annuel couvre 12 mois à partir du mois choisi et se dépose une seule fois. `valid_until` est calculé, pas saisi.
- **Contrôles :** montant > 0 et ≤ 1 000 (« Le montant semble trop élevé. Vérifiez la saisie. ») ; fichier obligatoire, type et taille vérifiés côté serveur ; pas de chevauchement avec un justificatif actif du même type (« Un justificatif de ce type couvre déjà {mois}. »).
- **Validation :** RH. Le RH voit le fichier dans le détail (aperçu PDF ou image, URL signée).
- **Relance :** notification 15 jours avant la fin de validité d'un abonnement annuel.
- **Export paie (RH) :** justificatifs validés du mois avec montant et remboursement estimé.

## Critères d'acceptation

- Un salarié qui a 2 jours de télétravail (en attente ou validés) dans une semaine ne peut pas en déclarer un troisième ; le message cite la semaine et le maximum.
- Un manager ne voit dans « À valider » que les demandes de son équipe directe et ne peut pas valider sa propre demande.
- Un refus sans motif est bloqué ; le motif apparaît dans l'historique du demandeur.
- Envoyer une demande crée l'événement de planning en attente (hachuré) ; la validation finale le rend plein ; le refus ou l'annulation le supprime.
- « Annuler » dans la notification visuelle après une validation remet la demande « En attente » et retire la notification envoyée.
- Deux clics rapides sur « Valider » ne créent qu'une transition.
- Un justificatif de 6 Mo ou au format .exe est refusé avec un message explicite.
- Un salarié ne peut pas télécharger le justificatif d'un collègue, même avec l'URL.
