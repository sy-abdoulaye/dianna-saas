# Suivi du matériel

Route : `/materiel/`. Actions : « Ajouter un équipement » (RH), « Demander du matériel » (tous).

## Onglets

| Onglet | Profils | Contenu |
|---|---|---|
| Mon matériel | Tous | Équipements attribués (type, modèle, n° de série en Mono, état) avec « Signaler un problème » ; puis « Mes demandes de matériel » (tableau du moteur commun) |
| Mon équipe | Manager | Matériel attribué à son équipe, lecture seule |
| Parc | RH, Admin | Indicateurs (équipements, en stock, en réparation), filtres (recherche, type, état), tableau avec actions selon l'état : Attribuer et Réparation (en stock), Restituer (attribué), Remettre en stock (en réparation) |
| Demandes | RH, Admin | Demandes de matériel à valider et historique (moteur commun). Une demande validée affiche « Attribuer un équipement » (choix parmi le stock du type demandé) ; l'attribution est liée à la demande |
| Signalements | RH, Admin | Signalements ouverts et clos : équipement, auteur, description ; actions « Envoyer en réparation » (l'équipement passe en réparation, son détenteur est conservé) et « Clore » (résolution obligatoire) |

## Modales

- **Demander du matériel :** Équipement (Ordinateur portable, Écran, Casque audio, Téléphone, Autre), Motif (obligatoire).
- **Signaler un problème :** description obligatoire ; notifie les RH ; crée un `EquipmentIssue`.
- **Attribuer :** collaborateur (obligatoire) ; notifie la personne ; annulable depuis la notification visuelle.
- **Ajouter un équipement :** type, modèle, n° de série (obligatoire, unique : « Ce numéro de série existe déjà dans le parc. »).
- **Restituer :** confirmation ; l'équipement repasse en stock ; l'historique d'attribution est fermé.
- **Retirer du parc :** confirmation destructive ; statut « Retiré » ; réservé aux équipements en stock ou en réparation ; masqué par défaut dans le Parc (filtre État).

## Règles

- Un équipement n'a qu'un détenteur à la fois. Attribuer un équipement déjà attribué est impossible.
- Archivage d'un salarié : alerte aux RH s'il détient encore du matériel (liste à restituer).
- Historique complet par équipement (attributions, réparations, signalements).

## Critères d'acceptation

- Un salarié ne voit pas l'onglet Parc et reçoit 403 sur ses URL.
- Attribuer puis « Annuler » remet l'équipement en stock et retire la notification.
- Archiver un salarié qui détient un ordinateur affiche l'alerte de restitution.
