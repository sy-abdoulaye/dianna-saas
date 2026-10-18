# Produit

## Vision

Dianna remplace les tableurs, e-mails et formulaires papier qui servent à gérer le télétravail, les congés d'été, les astreintes, les justificatifs de transport, le matériel, le planning et la communication interne. Elle est simple pour le salarié, et donne aux managers et aux RH une vue claire et des validations en quelques clics.

- **Cible :** PME et ETI françaises de 50 à 1 000 salariés, population mixte (bureau, terrain, équipes d'astreinte).
- **Acheteur :** DRH ou direction générale. **Utilisateurs quotidiens :** salariés et managers.
- **Modèle :** abonnement par salarié et par mois, avec des packs de modules.
- **Principe :** une entreprise cliente = un espace isolé (tenant). Un noyau obligatoire, des modules activables.

## Profils

| Profil | Rôle | Périmètre |
|---|---|---|
| Salarié | Déclare et suit ses demandes, consulte l'annuaire et le planning de son service, répond aux questionnaires, rédige ses comptes rendus d'intervention | Lui-même |
| Manager | Tout ce que fait le salarié, plus : valide les demandes de son équipe, conduit les entretiens, valide les comptes rendus, consulte les résultats de questionnaires | Son équipe directe |
| RH | Gère les fiches, valide transport et matériel, publie annonces et questionnaires, pilote les campagnes, consulte tout | Toute l'entreprise |
| Administrateur | Tout ce que font les RH, plus : paramètres de l'entreprise, profils d'accès, services et sites, modules, journal d'activité | Toute l'entreprise |
| Super-administrateur éditeur | Équipe Dianna : crée les entreprises, active les modules, suspend un client. Pas d'accès aux données métier sans accès support tracé | Plateforme |

Un manager est un salarié qui a une équipe : son profil d'accès est « Manager », et son équipe est l'ensemble des fiches dont il est le manager direct.

## Modules et périmètre

| Module | Statut | Fiche |
|---|---|---|
| Socle : connexion, entreprise, profils, notifications, journal | V1, obligatoire | `modules/01-socle.md` |
| Tableau de bord | V1 | `modules/02-tableau-de-bord.md` |
| Annuaire | V1 | `modules/03-annuaire.md` |
| Administration | V1 | `modules/04-administration.md` |
| Demandes : télétravail, congés estivaux, astreintes, transport | V1 | `modules/05-demandes.md` |
| Planning et export du planning | V1 | `modules/06-planning.md` |
| Suivi du matériel | V1 (lot 5) | `modules/07-materiel.md` |
| Communication interne | V1 | `modules/08-annonces.md` |
| Questionnaires | V1 (lot 6) | `modules/09-questionnaires.md` |
| Carrière et évaluations | V1 (lot 7) | `modules/10-carriere.md` |
| Suivi d'intervention | V1 (lot 7) | `modules/11-interventions.md` |
| Plan de charge | Plus tard (page « Bientôt ») | — |
| Recrutement | Plus tard (page « Bientôt ») | — |

Hors périmètre : paie et bulletins, badgeuse et décompte légal du temps de travail, contrats et signature électronique qualifiée, notes de frais.

## Principes d'expérience

- Chaque demande a un **statut visible** (en attente, validée, refusée, annulée) et un **historique**.
- Chaque action importante donne un **retour immédiat** : notification visuelle avec, quand c'est possible, un lien vers l'objet et un bouton Annuler.
- Ce qu'un profil ne peut pas faire **n'est pas affiché**. Une donnée réservée porte la mention « Réservé aux RH » plutôt qu'un blanc.
- **Mobile d'abord** pour le salarié (déclarations), bureau pour les managers et les RH (validation, planning, exports).
- **Fenêtres de saisie courtes** pour les demandes, **pages complètes** pour les formulaires longs (fiche salarié, entretien, compte rendu).

## Glossaire

| Terme | Sens |
|---|---|
| Entreprise (tenant) | Client de Dianna, espace isolé. Modèle `Company` |
| Fiche salarié | Données d'une personne dans une entreprise. Modèle `Employee` |
| Compte | Identité de connexion. Modèle `User` |
| Demande | Télétravail, congé, astreinte, justificatif de transport, demande de matériel. Suit un circuit de validation |
| Événement de calendrier | Projection d'une demande dans le planning. Modèle `CalendarEvent`, commun à tous les modules |
| Campagne | Période de collecte : congés d'été, entretiens annuels |
| Compte rendu d'intervention | Bilan mensuel d'un salarié sur une intervention (mission client ou projet) |
