# Socle : entreprise, comptes, navigation, notifications, journal

## Écrans

| Route | Écran |
|---|---|
| `dianna.fr` | Page vitrine minimale : « Accéder à mon espace » (saisie de l'e-mail, redirection vers le sous-domaine de l'entreprise, T-08) |
| `/connexion/` | E-mail, mot de passe, « Mot de passe oublié ». Logo de l'entreprise si le sous-domaine est connu |
| `/connexion/2fa/` | Code de double authentification (RH, Admin) |
| `/invitation/<token>/` | Création du mot de passe à la première connexion ; lien expiré : message et bouton « Demander une nouvelle invitation » (notifie l'administrateur) |
| Mise en page | Menu latéral (groupes : sans titre, Demandes, Activité, Talents, Entreprise), compteurs « à traiter » par module, barre du haut avec recherche globale, cloche, menu utilisateur (Ma fiche, Thème, Se déconnecter) |
| `/notifications/` | Liste complète des notifications (la cloche montre les 8 dernières) |
| Pages d'erreur | 403 « Accès non autorisé », 404 « Page introuvable », « Module désactivé », entreprise suspendue |

## Règles

- Le menu n'affiche que les modules activés et autorisés pour le profil (Administration : Admin seulement). Recrutement et Plan de charge : visibles, marqués « Bientôt », non cliquables, info-bulle « Disponible dans une prochaine version » ; pas de page d'information (L1-01).
- L'administration éditeur est servie uniquement sur `admin.dianna.fr` (double authentification obligatoire) ; un membre de l'équipe Dianna n'a aucun droit particulier sur un sous-domaine client (T-22).
- Recherche globale : suggestions de collaborateurs dès le premier caractère (5 au maximum) ; Entrée ouvre l'annuaire filtré.
- Notifications : créées par les services ; la cloche affiche le nombre non lu ; un clic marque comme lu et ouvre l'objet. E-mail envoyé en tâche de fond pour les types listés en M-16.
- Journal d'audit : écrit par les services pour les actions de `02-architecture.md` (section Sécurité).
- Session : expiration après 12 h d'inactivité ; « Se déconnecter » invalide la session.

## Critères d'acceptation

- Un utilisateur de l'entreprise A qui ouvre l'URL d'un objet de l'entreprise B reçoit une 404.
- Un salarié qui ouvre `/administration/` reçoit la page « Accès non autorisé ».
- Un module désactivé disparaît du menu de tous les utilisateurs et son URL affiche « Module désactivé ».
- Un RH ou un administrateur doit enregistrer la double authentification à sa première connexion (et quand son profil change vers RH ou Admin), puis ne peut plus se connecter sans code.
- Une invitation expirée ne permet pas de créer un mot de passe.
- La cloche affiche les notifications du seul utilisateur connecté.
