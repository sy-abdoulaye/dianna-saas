# Note de livraison : lot 1, socle multi-entreprise et comptes

Date : 19 octobre 2026. Branche : `lot-1`.

## Ce qui est fait

**Isolation entre entreprises (commencée en premier).**
- `TenantModel` et `TenantManager` : filtre automatique, `NoCurrentCompanyError` sans entreprise courante, entreprise posée à l'enregistrement, écriture refusée sur un objet d'une autre entreprise, clés étrangères vérifiées dans la même entreprise.
- `CompanyMiddleware` : vitrine, éditeur ou espace client selon l'hôte ; sous-domaine inconnu en 404 ; entreprise suspendue sur une page dédiée ; contexte remis à zéro après chaque requête.
- `EmployeeMiddleware` : une session présentée sur un autre hôte est fermée.
- **Batterie réutilisable** : fixtures à deux entreprises équivalentes (`company_a`, `company_b`, `client_for`) et registre `tests/isolation.py`. Deux garde-fous automatiques : tout modèle de `apps/` doit hériter de `TenantModel`, et toute route à paramètre de l'espace client doit être déclarée dans le registre, sinon les tests échouent.

**Comptes (T-09, T-10).**
- `Employee` séparé de `User`, invitation de 7 jours (empreinte du jeton seulement), lien expiré avec « Demander une nouvelle invitation » (administrateurs prévenus une fois).
- Adresse déjà utilisée sur Dianna refusée avec le message prévu.
- Connexion par e-mail avec allauth 65.19.1 sous `/connexion/`, mot de passe oublié limité aux comptes de l'espace, session de 12 h, déconnexion.
- Double authentification TOTP imposée par middleware aux RH, aux administrateurs et à l'équipe Dianna, à la première connexion et dès un passage à RH ou Admin. `DEMO_DISABLE_2FA` est refusé par un contrôle système si `DEBUG` est faux.

**Permissions.** `apps/core/permissions.py` code toute la matrice de `04-permissions.md`.
- La colonne « Manager » dépend des collaborateurs directs, pas du profil (L1-02).
- Personne ne décide pour soi-même.
- Contrôles des vues : `permission_required`, `PermissionRequiredMixin`, `module_required`.
- Pages 403 (avec le profil), 404, « Module désactivé », 500 et entreprise suspendue. Elles s'affichent dans la mise en page de l'application quand l'utilisateur est connecté.

**Socle.**
- Menu filtré par module activé et par profil ; « Bientôt » visible, non cliquable, avec l'info-bulle (L1-01).
- Cloche (8 dernières, « Tout marquer comme lu »), page `/notifications/`, ouverture qui marque comme lu (liens externes refusés).
- Journal d'audit écrit par les services.
- Thème enregistré dans `User.theme` et repris sur un autre appareil.
- Tableau de bord réduit à l'en-tête.

**Hôtes (T-08, T-22).**
- Vitrine « Accéder à mon espace ».
- Administration éditeur sur `admin.<domaine>` avec double authentification. Elle crée l'entreprise, active tous ses modules, crée la fiche du premier administrateur et l'invite. Elle affiche les modules de l'entreprise et ne montre que les comptes de l'équipe Dianna.

**Démonstration.**
- `make seed` charge Exemple SAS (24 personnes du prototype, 4 comptes de démonstration) et Autre SA (4 personnes, un compte administrateur).
- `--reset` recharge les données.
- La commande est refusée si `DEBUG` est faux.

## Tests

| Commande | Résultat |
|---|---|
| `make lint` | sans erreur |
| `make test` | 161 tests ; couverture : `permissions.py` 99 %, `accounts/services.py` 95 %, `core/services.py` 97 %, total 96 % |
| `make e2e` | 25 parcours, dont le parcours 8 (isolation) et les 4 profils |
| `make check` | aucune alerte, dont `--deploy` |

## Critères d'acceptation de la fiche socle

| Critère | État |
|---|---|
| Objet d'une autre entreprise : 404 | Fait, vérifié par la batterie et par Playwright |
| Salarié sur `/administration/` : « Accès non autorisé » | Contrôle prêt et testé (`admin.manage`). La route arrive avec l'écran d'administration au lot 2 |
| Module désactivé : absent du menu, URL « Module désactivé » | Menu et décorateur faits et testés. Aucun écran de module n'existe encore ; le parcours complet arrive avec le premier module (lot 2 ou 3) |
| Double authentification RH et Admin | Fait (inscription imposée, code à chaque connexion) |
| Invitation expirée | Fait |
| Cloche limitée à l'utilisateur | Fait |

## Écarts et points à relire

- Décisions prises pendant le lot : L1-10 à L1-17 dans `00-decisions.md`, statut « À confirmer ».
- **Vitrine (L1-12).** La redirection révèle à quelle entreprise appartient une adresse connue. Une variante plus discrète enverrait le lien par e-mail.
- **Données de démonstration.** Louise Martin a 5 collaborateurs directs dans le prototype ; `07-donnees-de-demo.md` parlait d'une « équipe de 6 ». La fiche est précisée.
- **Écrans d'allauth.** Les écrans principaux (connexion, mot de passe oublié, code, activation) utilisent les composants de Dianna. Les écrans secondaires (codes de secours, sécurité du compte) passent par les éléments d'allauth restylés.
