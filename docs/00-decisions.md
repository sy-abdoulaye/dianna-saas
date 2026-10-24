# Décisions techniques et métier

Chaque ligne a un statut : **Validé** (décidé par le porteur du projet) ou **À confirmer** (recommandation appliquée par défaut tant qu'elle n'est pas modifiée). Pour changer une décision, modifie la ligne, passe-la en Validé et note la date.

Versions vérifiées le 18 octobre 2026.

## Déjà validé

| ID | Sujet | Décision | Statut |
|---|---|---|---|
| V-01 | Stack | Python, Django, PostgreSQL, templates Django, HTML5, Tailwind CSS, JavaScript, HTMX si nécessaire | Validé |
| V-02 | Nom du produit | Dianna | Validé |
| V-03 | Marché | France d'abord, interface en français | Validé |
| V-04 | Design | Design system et prototype interactif validés (18 oct. 2026) | Validé |
| V-05 | Thèmes | Clair, sombre et « système » | Validé |
| V-06 | Profils | 4 profils d'entreprise : Salarié, Manager, RH, Administrateur (en attendant un modèle plus fin) | Validé |
| V-07 | Annuaire | Vue liste et vue cartes avec photo ; comme tout salarié, le manager voit les coordonnées professionnelles de tous, mais les informations RH (contrat, matricule…) de personne d'autre que lui, y compris son équipe | Validé |
| V-08 | Paie | Hors périmètre | Validé |
| V-09 | Questionnaires | Commentaire facultatif sur chaque note | Validé |
| V-10 | Suivi d'intervention | Travaux réalisés, travaux prévus, visibilité, prolongation et suivi | Validé |

## Technique : à confirmer

| ID | Sujet | Recommandation | Alternative | Statut |
|---|---|---|---|---|
| T-01 | Version de Python | Python 3.13, environnement et dépendances gérés par **uv** (`pyproject.toml`, `uv.lock`) | 3.14 si toutes les dépendances la supportent | Validé (18 oct. 2026) |
| T-02 | Version de Django | Django **6.1** pour démarrer, puis passage à **6.2 LTS** (prévue en avril 2027) avant la mise en production | 5.2 LTS (sécurité jusqu'en avril 2028), plus conservatrice mais sans les fragments de templates ni la CSP intégrés | Validé (18 oct. 2026) |
| T-03 | PostgreSQL | 18 (version stable actuelle ; la 19 est en release candidate) | 17 si l'hébergeur ne propose pas encore la 18 | À confirmer |
| T-04 | Tailwind CSS | Tailwind v4, **binaire autonome** téléchargé par le `Makefile` (version et somme SHA-256 fixées dans le `Makefile`), sans paquet Python ni Node | npm + Tailwind CLI si une chaîne Node existe déjà | Validé (18 oct. 2026) |
| T-05 | HTMX | **2.x** avec `django-htmx`. La 4.0 (sortie le 28 août 2026) change l'héritage des attributs et les noms d'événements ; on migrera plus tard | 4.0 directement | À confirmer |
| T-06 | Fragments HTMX | Fragments intégrés à Django 6 (`{% partialdef %}`) pour les résultats de liste d'une page ; fichiers `templates/<app>/partials/` pour les fragments réutilisés (modales, lignes, blocs communs) | `django-template-partials` | Validé (18 oct. 2026) |
| T-07 | Architecture multi-entreprise | Une base, un schéma, colonne `company_id` sur chaque table métier, gestionnaire filtrant automatiquement, entreprise résolue par le middleware. Défense en profondeur par Row Level Security PostgreSQL au lot 8 | Un schéma par entreprise (`django-tenants`) : isolation plus forte, mais migrations et opérations plus lourdes | À confirmer |
| T-08 | Accès des entreprises | Sous-domaine par entreprise (`exemple.dianna.fr`). `dianna.fr` : page vitrine minimale avec « Accéder à mon espace » (saisie de l'e-mail, lien vers le sous-domaine de l'entreprise envoyé par e-mail, L1-12) | Domaine unique et choix de l'entreprise à la connexion | Validé (18 oct. 2026) |
| T-09 | Comptes | `User` personnalisé, connexion par e-mail. `User.email` est l'identifiant de connexion, `Employee.email` le contact professionnel. À l'invitation, le compte est créé avec l'e-mail de la fiche ; modifier l'e-mail de la fiche ne change pas l'identifiant ; changer d'identifiant est une action séparée confirmée par e-mail. Un compte appartient à une seule entreprise en V1 : inviter une adresse déjà utilisée dans une autre entreprise est refusé (« Cette adresse est déjà utilisée sur Dianna. Utilisez une autre adresse ou contactez le support. ») | — | Validé (18 oct. 2026) |
| T-10 | Authentification | `django-allauth` 65.19.1 (compatibilité Django 6.1 vérifiée au début du lot 1), monté sous `/connexion/` : e-mail et mot de passe, réinitialisation, TOTP. Double authentification obligatoire pour RH, Administrateur et équipe Dianna, imposée par un **middleware maison** (inscription forcée à la première connexion et quand le profil passe à RH ou Admin) ; désactivable en développement par `DEMO_DISABLE_2FA` (refusé si `DEBUG = False`). SSO Google et Microsoft au lot 8 | Authentification Django native et code maison | Validé (18 oct. 2026) |
| T-11 | Tâches en arrière-plan | Cadre de tâches de Django 6 (`django.tasks`) avec le moteur base de données du paquet `django-tasks-db` **0.13.0** (épinglé) : pas de Redis à opérer | Celery + Redis si le volume l'exige | Validé par L3-01 (20 oct. 2026) |
| T-12 | Fichiers | Stockage objet S3 Scaleway Object Storage (fr-par), `django-storages[s3]` **1.14.6** et `boto3` **1.43.116**, un bucket privé par environnement, chiffrement côté serveur. Photos et logos : URL signées de 5 minutes (A2-07) ; justificatifs : jamais de lien signé (L5-01) | Stockage disque local (développement et tests) | Validé (21 oct. 2026), compte créé au lot 8 |
| T-13 | E-mails | `django-anymail` avec un fournisseur européen (Brevo ou Scaleway Transactional Email) | — | À confirmer |
| T-14 | Hébergement | Conteneurs Docker chez un hébergeur français (Scaleway, OVHcloud ou Clever Cloud), PostgreSQL managé avec sauvegardes quotidiennes | — | À confirmer |
| T-15 | Exports | CSV (module `csv`, séparateur point-virgule, encodage UTF-8 avec BOM pour Excel), Excel (`openpyxl` **3.1.5**), iCalendar écrit sans dépendance (L4-05), PDF (`WeasyPrint` **70.0**, récupérateur d'URL fermé, L4-06) | — | Validé (21 oct. 2026) |
| T-16 | Jours fériés | Paquet `holidays` **0.107** (France ; Alsace-Moselle par site, L4-02), complété par les fermetures saisies par l'administrateur | — | Validé (21 oct. 2026) |
| T-17 | Tests | `pytest`, `pytest-django`, `factory_boy`, couverture ≥ 85 % sur `services.py` et `permissions.py`, parcours de bout en bout avec Playwright | — | À confirmer |
| T-18 | Qualité | `ruff` (lint et format), `djlint` (templates), `pre-commit`, intégration continue GitHub Actions | — | À confirmer |
| T-19 | Configuration | Variables d'environnement (`django-environ`), réglages séparés `base`, `dev`, `test`, `prod` | — | À confirmer |
| T-20 | Polices | IBM Plex Sans, IBM Plex Mono et Schibsted Grotesk hébergées dans `static/fonts/` (licence OFL), pas d'appel à Google Fonts en production (RGPD) | — | À confirmer |
| T-21 | Supervision | Sentry (région UE) et journaux structurés sans données personnelles | Solution auto-hébergée | À confirmer |
| T-22 | Super-administration éditeur | Administration Django réservée à l'équipe Dianna, servie **uniquement sur `admin.dianna.fr`** en production (`/editeur/` en développement), double authentification obligatoire. Un membre de l'équipe Dianna n'a **aucun droit particulier** sur un sous-domaine client. Aucun accès aux données métier sans accès support tracé (lot 8) | Back-office dédié plus tard | Validé (18 oct. 2026) |

## Décisions du lot 0

| ID | Sujet | Décision | Statut |
|---|---|---|---|
| L0-01 | Modèle utilisateur | `accounts.User` créé dès le lot 0, avant la première migration : connexion par e-mail, `PermissionsMixin`, `is_staff` (accès à l'administration Django de l'éditeur) | Validé (18 oct. 2026) |
| L0-02 | Barres de progression et CSP | Éléments natifs `<progress>` et `<meter>`, stylés en CSS. Aucun attribut `style`, aucun `'unsafe-inline'` dans la CSP | Validé (18 oct. 2026) |
| L0-03 | Annulation immédiate | Fenêtre de **30 s** côté serveur (la notification peut rester affichée plus longtemps au survol). Après expiration : notification d'erreur « Il est trop tard pour annuler cette action. ». Les e-mails liés à une action annulable partent après **45 s** | Validé (18 oct. 2026) |
| L0-04 | Thème sans JavaScript | Repli `prefers-color-scheme` dans `app.css` en plus de `data-theme`, comme le prototype | Validé (18 oct. 2026) |
| L0-05 | Branche principale | `main` | Validé (18 oct. 2026) |
| L0-06 | Dépendances ajoutées | `psycopg` 3 (pilote PostgreSQL), `whitenoise` (fichiers statiques), `gunicorn` (serveur), `django-htmx`, `pytest-cov` (couverture), `pytest-playwright` (parcours de bout en bout sans Node) | Validé (18 oct. 2026) |
| L0-07 | Ressources front copiées dans le dépôt | HTMX 2.0.11 (`static/vendor/`), icônes `lucide-static` 1.50.0 (sprite généré), polices Fontsource 5.3.0 (sous-ensemble latin, woff2, licence OFL) : aucun appel à un CDN, compatible avec la CSP | Validé (18 oct. 2026) |
| L0-08 | Port PostgreSQL de développement | **5434** sur l'hôte (un PostgreSQL local occupe souvent 5432), réglable par `DB_PORT` dans `docker-compose.yml` | Validé (18 oct. 2026) |
| L0-09 | Envoi des e-mails | Réglage `MAILERS` de Django 6.1 (`EMAIL_BACKEND` est déprécié), variable `MAIL_BACKEND` ; console en développement. **Lot 8 :** vérifier que `django-anymail` fonctionne avec `MAILERS` | Validé (18 oct. 2026) |
| L0-10 | Icônes | Icônes Lucide (design system) sous les clés courtes du prototype (`dash`, `users`, `home`…) ; correspondance dans `scripts/vendor_assets.py`. Le prototype dessinait ses propres tracés | Validé (18 oct. 2026) |
| L0-11 | Configuration HTMX | `allowEval` désactivé, `historyCacheSize: 0` (aucune copie de page RH dans le `localStorage`), `attributesToSettle` sans `style` (CSP), styles d'indicateur dans `app.css` | Validé (18 oct. 2026) |
| L0-12 | Onglets | Liens de navigation (une URL par onglet, `aria-current="page"`), pas de `role="tablist"` : l'onglet est dans l'URL et le bouton Retour fonctionne | Validé (18 oct. 2026) |
| L0-13 | Administration de l'éditeur | `/editeur/` en développement seulement ; en production, `admin.dianna.fr` (T-22) | Validé (18 oct. 2026) |
| L0-14 | Pages d'erreur | Rendues dans la mise en page d'authentification tant qu'il n'y a pas d'utilisateur connecté (lot 1). « Module désactivé » répond 403 | Validé (18 oct. 2026) |
| L0-15 | Journal d'accès | Gunicorn journalise méthode, chemin, statut et durée, sans query string ni adresse IP (les recherches contiennent des noms) | Validé (18 oct. 2026) |
| L0-16 | Notifications et modales | Pendant qu'une modale est ouverte, la zone des notifications est placée dans la modale pour rester visible et cliquable | Validé (18 oct. 2026) |

## Décisions de préparation du lot 1 (18 oct. 2026)

| ID | Sujet | Décision | Statut |
|---|---|---|---|
| L1-01 | Entrées « Bientôt » du menu | Visibles mais non cliquables, info-bulle « Disponible dans une prochaine version ». Pas de page d'information | Validé (18 oct. 2026) |
| L1-02 | Valideur et équipe | Le valideur est le **manager direct, quel que soit son profil**. Toute fiche active peut être choisie comme manager. Les droits « Équipe » de `04-permissions.md` découlent du fait d'avoir des collaborateurs directs, **pas du profil** ; le profil « Manager » n'ajoute aucun droit à lui seul | Validé (18 oct. 2026) |
| L1-03 | Routes | Chemins visibles en français, noms de routes et code en anglais | Validé (18 oct. 2026) |
| L1-04 | « Arrivée prochaine » | Visible de tous avec son badge, comptée dans le filtre « En poste » | Validé (18 oct. 2026) |
| L1-05 | Annuaire | Fait partie du socle, non désactivable (retiré des modules activables) | Validé (18 oct. 2026) |
| L1-06 | Planning d'un manager | Son service, plus les membres de son équipe directe rattachés à d'autres services | Validé (18 oct. 2026) |
| L1-07 | Astreinte au planning | Elle se cumule avec les autres états : la case montre l'état principal (congé > télétravail > sur site) et un repère « A » | Validé (18 oct. 2026) |
| L1-08 | Annulation après envoi | La demande est supprimée ; le journal d'audit garde « demande envoyée puis retirée » | Validé (18 oct. 2026) |
| L1-09 | Anonymat des questionnaires | Risque résiduel accepté pour la V1 : rapprochement possible en base, par un accès SQL direct, quand les réponses sont peu nombreuses. (1) Ordre physique des lignes. (2) Numéro de transaction (`xmin`, ajouté au lot 6) : la réponse est écrite dans la transaction du service et le reçu dans une sous-transaction, ouverte juste avant ; le `xmin` du reçu vaut celui de la réponse + 1 (test `test_residual_link_in_the_database_by_transaction_number`). (3) Sauvegardes : `pg_dump` écrit les lignes dans leur ordre physique, donc une sauvegarde garde le lien, même après la réécriture groupée du lot 8 pour les sauvegardes antérieures ; leur conservation et leur accès sont à traiter avec la politique de sauvegarde (lot 8). La date a été retirée des réponses (L6-02). L'application ne lit jamais ces colonnes. À revoir au lot 8 | Validé (18 oct. 2026, complété les 24 et 25 oct.) |

## Décisions prises pendant le lot 1 (19 oct. 2026)

| ID | Sujet | Décision | Statut |
|---|---|---|---|
| L1-10 | Routage par hôte | `CompanyMiddleware` choisit les routes selon l'hôte : `config.urls_public` (vitrine), `config.urls_platform` (éditeur), `config.urls` (espace client). En développement : `localhost:8000`, `admin.localhost:8000` et `<slug>.localhost:8000` ; `/editeur/` reste aussi disponible sur `localhost` (L0-13) | Validé (19 oct. 2026) |
| L1-11 | Connexion liée à l'hôte | Un compte ne se connecte que sur le sous-domaine de son entreprise (même message qu'un mauvais mot de passe) ; une session présentée sur un autre hôte est fermée. L'équipe Dianna ne se connecte que sur l'hôte éditeur | Validé (19 oct. 2026) |
| L1-12 | Vitrine et confidentialité | **Variante discrète** : la page affiche toujours « Si cette adresse correspond à un compte Dianna, vous allez recevoir un lien de connexion par e-mail. » ; le lien vers le sous-domaine de l'entreprise part par e-mail. Plus d'exception CSP. Limite : 10 essais par 10 minutes par adresse IP réelle (X-Forwarded-For selon `TRUSTED_PROXY_COUNT`) et 3 par adresse saisie (empreinte HMAC). Écart de temps de réponse quand un e-mail part : supprimé au lot 3 (envoi en tâche de fond) | Validé (19 oct. 2026) |
| L1-13 | Mot de passe oublié | Le lien n'est envoyé qu'aux comptes de l'espace où la demande est faite ; une adresse inconnue ne reçoit aucun e-mail (`ACCOUNT_EMAIL_UNKNOWN_ACCOUNTS = False`) ; la réponse est la même dans tous les cas | Validé (19 oct. 2026) |
| L1-14 | E-mail d'invitation | Envoyé par une tâche en arrière-plan, sans délai, depuis le lot 3 (T-11). Le jeton est créé par la tâche au moment de l'envoi ; son empreinte n'est enregistrée qu'une fois l'e-mail accepté par le serveur d'envoi. En cas d'échec, l'invitation précédente reste valable et la nouvelle est marquée « Envoi échoué » dans « Utilisateurs et profils », avec « Renvoyer l'invitation » (A3-04) | Validé (19 oct. 2026), mis à jour au lot 3 |
| L1-15 | Suppression d'un service ou d'un site | Clés étrangères des fiches en `RESTRICT` : un service ou un site utilisé ne peut pas être supprimé, mais la suppression d'une entreprise entière reste possible | Validé (19 oct. 2026) |
| L1-16 | Cache et limites de fréquence | Les limites de fréquence de Dianna (vitrine, exports) sont comptées en base, pas dans le cache : `RateLimitCounter` (empreinte HMAC de la clé, début de fenêtre, nombre ; contrainte unique), incrémenté en une seule requête PostgreSQL atomique (`INSERT … ON CONFLICT DO UPDATE SET count = count + 1 RETURNING count`, `apps/core/ratelimit.py`) ; fenêtres expirées supprimées par `purge_task_results`. Le cache reste mémoire en développement et base de données en production (`createcachetable` au déploiement) pour les limites internes d'allauth (connexion, mot de passe oublié) | Validé (19 oct. 2026), corrigé le 21 oct. 2026 |
| L1-17 | Écrans du lot 1 | Tableau de bord réduit à l'en-tête et à l'état « Tout est à jour » ; recherche globale et « Ma fiche » masquées jusqu'à l'annuaire (lot 2) ; logo de l'entreprise reporté au lot 2 (stockage des fichiers, T-12), son nom est affiché à la connexion ; pas de notification visuelle à la connexion et à la déconnexion | Validé (19 oct. 2026) |

## Audit du lot 1 (19 oct. 2026)

| ID | Sujet | Décision | Statut |
|---|---|---|---|
| A1-01 | Administration éditeur | Seuls `Company` (avec `CompanyModule` en ligne) et les comptes de l'équipe Dianna sont inscrits ; `mfa.Authenticator`, `account.EmailAddress` et `auth.Group` sont retirés ; un test échoue si un autre modèle est inscrit. Pas de suppression d'entreprise (procédure RGPD au lot 8) | Validé (19 oct. 2026) |
| A1-02 | Secrets de double authentification | Chiffrés par `MultiFernet` avec `MFA_ENCRYPTION_KEY` (distincte de `SECRET_KEY`, obligatoire en production, plusieurs clés pour en changer) ; dépendance `cryptography` ajoutée | Validé (19 oct. 2026) |
| A1-03 | Relations entre objets métier | Clés étrangères, relations un-à-un (`save`) et plusieurs-à-plusieurs (`m2m_changed`) vérifiées dans la même entreprise ; pas de `update()` ni de `bulk_create` sur ces relations sans vérification explicite (CLAUDE.md) | Validé (19 oct. 2026) |
| A1-04 | Propriétaire des objets | Chaque modèle soumis aux permissions déclare `permission_owner_field` ; un propriétaire vide refuse l'accès | Validé (19 oct. 2026) |
| A1-05 | Réinitialisation du mot de passe | La clé n'est acceptée que sur l'hôte de l'entreprise du compte (ou l'hôte éditeur pour l'équipe Dianna) | Validé (19 oct. 2026) |
| A1-06 | Cookies en production | `__Host-sessionid` et `__Host-csrftoken` : sans Domain, `Path=/`, `Secure` | Validé (19 oct. 2026) |
| A1-07 | Adresse IP du client | Lue derrière `TRUSTED_PROXY_COUNT` proxys de confiance (journal d'audit, vitrine, allauth) | Validé (19 oct. 2026) |

## Décisions prises pendant le lot 2 (19 oct. 2026)

| ID | Sujet | Décision | Statut |
|---|---|---|---|
| L2-01 | Fichiers privés | Photos et logo sur un stockage disque privé (`PRIVATE_MEDIA_ROOT`, hors des fichiers statiques), noms aléatoires rangés par entreprise, servis par URL signée de 5 minutes liée à l'entreprise. Le stockage objet S3 (T-12) arrive au lot 5 avec les justificatifs | Validé (20 oct. 2026) |
| L2-02 | Images | Dépendance **Pillow 12.3** ajoutée : type vérifié côté serveur, 40 millions de pixels au plus (lus sur l'en-tête, avant décodage), image reconstruite à partir de ses seuls pixels et réencodée : aucune métadonnée conservée (EXIF dont la position GPS, commentaire JPEG, XMP, profil ICC, textes PNG). Photo : JPG ou PNG, 2 Mo, réduite à 512 px. Logo : PNG ou JPG, 1 Mo (pas de SVG, qui peut contenir du script) | Validé (20 oct. 2026) |
| L2-03 | Fiche « Parti » | Pour qui ne voit pas les départs, l'URL d'une fiche partie renvoie 404 (le prototype affichait « Accès non autorisé ») : son existence n'est pas révélée | Validé (20 oct. 2026) |
| L2-04 | Fiche : éléments des lots suivants | Onglet « Demandes » et raccourcis (fiche de suivi, demandes) masqués jusqu'aux lots 3 et 7 (règle 6) | Validé (20 oct. 2026) |
| L2-05 | Archivage | Date de départ modifiable dans la confirmation (aujourd'hui par défaut) ; impossible d'archiver sa propre fiche ou le dernier administrateur actif ; seul un administrateur archive une fiche de profil Administrateur (A2-06) ; annulation pendant 30 s depuis la notification | Validé (20 oct. 2026) |
| L2-06 | Import CSV | Aucune invitation envoyée (envoi depuis « Utilisateurs et profils ») ; dates JJ/MM/AAAA ou AAAA-MM-JJ ; UTF-8 ou Windows-1252 (Excel) ; 1 000 lignes et 1 Mo au plus ; manager présent dans l'annuaire ou dans le fichier ; contrat CDI, CDD, Alternance ou Stage ; longueurs contrôlées d'après les modèles ; fichier malformé (octet nul, encodage, champ trop long) refusé avec un message, jamais d'erreur 500 ; confirmation sans aperçu en session : « L'import a expiré. Recommencez. » | Validé (20 oct. 2026) |
| L2-07 | Utilisateurs et profils | Liste de toutes les fiches en poste avec l'état du compte (actif, invitation envoyée, pas de compte) et l'envoi ou le renvoi de l'invitation | Validé (20 oct. 2026) |
| L2-08 | Onglet « Entreprise » | Champs de la fiche administration (nom, quota de télétravail, M-02, M-03, logo) ; pas la campagne d'été du prototype, gérée dans le module Congés | Validé (20 oct. 2026) |
| L2-09 | Journal d'activité | Période par défaut : les 30 derniers jours ; export CSV de la période (point-virgule, UTF-8 avec BOM), lui-même journalisé | Validé (20 oct. 2026) |
| L2-10 | Tableau de bord initial | Indicateurs Administrateur (4) et RH (effectif en poste, arrivées à venir) seulement ; les autres blocs arrivent avec leurs modules | Validé (20 oct. 2026) |
| L2-11 | Changement d'identifiant de connexion | L'action séparée confirmée par e-mail (T-09) n'est pas encore livrée : le formulaire de fiche rappelle que l'identifiant ne suit pas l'e-mail de la fiche. Prévu au lot 8 (voir « Pour plus tard ») | Validé (20 oct. 2026) |
| L2-12 | Garde-fou d'isolation | Un queryset métier est lié à l'entreprise courante à sa construction ; à l'évaluation, erreur sans entreprise courante, avec une autre entreprise ou s'il a été construit sans entreprise (A2-01). Il peut être construit sans être lu (champs de `ModelForm` créés à l'import) | Validé (technique) |

## Audit du lot 2 (20 oct. 2026)

| ID | Sujet | Décision | Statut |
|---|---|---|---|
| A2-01 | Querysets métier | Liés à l'entreprise de leur construction : `NoCurrentCompanyError` sans entreprise courante, `CompanyMismatchError` si elle diffère ou si le queryset a été construit sans entreprise. Pas de queryset métier au niveau d'une classe (CLAUDE.md) : en production, vues et formulaires sont importés pendant la première requête d'un processus | Validé (20 oct. 2026) |
| A2-02 | Images trop grandes | 40 millions de pixels au plus (`MAX_IMAGE_PIXELS` dans `apps/core/files.py`), lus sur l'en-tête avant décodage ; `DecompressionBombWarning` de Pillow transformé en erreur ; message « Image trop grande. » | Validé (20 oct. 2026) |
| A2-03 | Exports CSV | Fonction commune `apps/core/csv_export.py` : toute cellule commençant par =, +, -, @, une tabulation ou un retour chariot est préfixée d'une apostrophe (injection de formules) ; règle dans CLAUDE.md | Validé (20 oct. 2026) |
| A2-04 | Profil d'accès | Tout changement de profil passe par `change_role` (fiche, création, administration) : son propre profil n'est pas modifiable, dernier administrateur protégé, journal `people.role_changed` ; sur sa propre fiche, le champ Profil n'est pas affiché | Validé (20 oct. 2026) |
| A2-05 | Photo à la création | L'entreprise est affectée avant l'enregistrement du fichier ; le chemin d'une photo lève une erreur sans entreprise (jamais de dossier `None/`) | Validé (20 oct. 2026) |
| A2-06 | Archivage d'un administrateur | Réservé aux administrateurs (`people.archive_admin`, docs/04-permissions.md) : « Seul un administrateur peut archiver un administrateur. » | Validé (20 oct. 2026) |
| A2-07 | Photos et logos : liens signés | Un lien signé de 5 minutes, utilisable sans connexion sur l'hôte de l'entreprise, est accepté pour les photos et les logos (le logo est affiché sur la page de connexion) | Validé (20 oct. 2026) |

## Préparation du lot 3 (20 oct. 2026)

| ID | Sujet | Décision | Statut |
|---|---|---|---|
| L3-01 | Tâches en arrière-plan (T-11) | `django-tasks-db` **0.13.0** épinglé, moteur base de données de `django.tasks`. Réserve : la version ne déclare que Django 6.0 ; un essai avec Django 6.1.2 (migrations, tâche immédiate, tâche différée) est concluant, à revérifier à chaque mise à jour. Le travailleur (`manage.py db_worker`) tourne en intégration continue (un test passe par une vraie tâche) et figure dans la documentation de déploiement | Validé (20 oct. 2026) |
| L3-02 | Congés d'été sans manager | Si l'étape RH est active et que le demandeur n'a pas de manager, la demande passe directement en validation finale RH, en une seule étape | Validé (20 oct. 2026) |
| L3-03 | Manager RH ou administrateur | Quand le manager direct est RH ou administrateur, sa validation est finale : personne ne valide deux fois | Validé (20 oct. 2026) |
| L3-04 | Télétravail dans le passé | Un jour passé est refusé ; aujourd'hui est permis | Validé (20 oct. 2026) |
| L3-05 | Quota de télétravail | Compté par semaine du lundi au dimanche ; la dérogation de la fiche remplace le quota de l'entreprise | Validé (20 oct. 2026) |
| L3-06 | Durée d'un congé | 31 jours calendaires au plus, week-ends compris | Validé (20 oct. 2026) |
| L3-07 | Chevauchement des astreintes | Refusé entre deux astreintes actives de la même personne ; pas de contrôle pour les interventions | Validé (20 oct. 2026) |
| L3-08 | Exports RH | Récapitulatifs mensuels du télétravail, export paie des astreintes et synthèse de campagne : lot 4 | Validé (20 oct. 2026) |
| L3-09 | Tableau de bord au lot 3 | Compteurs « à traiter » du menu et onglet « Demandes » de la fiche ; les blocs du tableau de bord restent au lot 4 | Validé (20 oct. 2026) |
| L3-10 | Annulation d'une demande validée | Par un RH ou un administrateur, motif obligatoire : `approved → cancelled`, événement de planning supprimé, notification et e-mail au demandeur, historique et journal. Le salarié n'annule que ses demandes en attente | Validé (20 oct. 2026) |
| L3-11 | E-mails d'allauth | Mot de passe oublié et autres e-mails d'allauth passent par les tâches, sans délai | Validé (20 oct. 2026) |

## Décisions prises pendant le lot 3 (20 oct. 2026)

| ID | Sujet | Décision | Statut |
|---|---|---|---|
| L3-12 | Jour ouvré | Du lundi au vendredi. Les jours fériés et les fermetures (T-16) ne sont pas encore exclus du télétravail : ils arrivent avec le planning (lot 4) | Validé (21 oct. 2026) |
| L3-13 | E-mails des demandes (M-16) | « À valider » au valideur, et décisions finales (validée, refusée, annulée) au demandeur : différés de 45 s, annulables. L'étape « Validée par le manager » notifie le demandeur et les RH dans l'application, et les RH par e-mail | Validé (21 oct. 2026) |
| L3-14 | Campagnes de congés d'été | Brouillon, puis Ouverte, puis Close ; date limite avant la période ; une seule ouverte (contrainte en base). Le type « Congés d'été » exige une campagne ouverte et des dates dans sa période ; sinon « Autre absence » | Validé (21 oct. 2026) |
| L3-15 | Seuil de conflit | Alerte renforcée quand les absents du service, demandeur compris, dépassent le seuil de la campagne en pourcentage de l'effectif en poste du service | Validé (21 oct. 2026) |
| L3-16 | Annulation immédiate d'un envoi validé automatiquement | Permise pendant 30 s comme un envoi ordinaire : la demande est retirée | Validé (21 oct. 2026) |
| L3-17 | Concurrence | Transitions sous `select_for_update` de la demande ; contrôles métier dans le service, sous verrou de la fiche du demandeur (envoi et annulations immédiates qui réactivent une demande, A3-02) ; contrainte unique partielle « une demande de télétravail active par jour », dont la violation devient un message | Validé (21 oct. 2026) |
| L3-18 | Éléments du lot 4 | Bouton « Voir le planning » et lien vers le planning du bandeau de campagne masqués jusqu'au lot 4 | Validé (21 oct. 2026) |

## Audit du lot 3 (20 oct. 2026)

| N° | Sujet | Décision | Statut |
|---|---|---|---|
| A3-01 | Annulation immédiate d'une décision | Le jeton porte l'événement créé par la transition ; l'annulation, sous verrou de la demande, n'est acceptée que si cet événement est toujours le dernier. Sinon 409 « Une autre décision a été prise depuis. Rien n'a été modifié. » et les notifications restent | Validé (20 oct. 2026) |
| A3-02 | Contrôles métier | Quota, même jour, chevauchements (congés, astreintes) et période de campagne dans `apps/approvals/workflow.py` (`check_request`), sous verrou de la fiche du demandeur, à l'envoi et aux annulations immédiates qui rendent une demande active (annulation, annulation d'une demande validée, et aussi refus). Les formulaires ne vérifient que leurs champs. Une `IntegrityError` devient un message, jamais une erreur 500 | Validé (20 oct. 2026) |
| A3-03 | Alerte de conflit | Calculée et affichée seulement pour qui peut décider (valideur, ou RH et administrateur à sa place). Le demandeur ne voit ni les noms ni le nombre, y compris dans la notification d'envoi | Validé (20 oct. 2026) |
| A3-04 | Données des tâches | Les e-mails de Dianna passent des identifiants à la tâche, le contenu est construit à l'envoi ; le jeton d'invitation est créé dans la tâche (seule son empreinte est enregistrée) ; les e-mails d'allauth sont chiffrés avec `TASKS_ENCRYPTION_KEY` (distincte, obligatoire en production). Résultat d'une tâche réussie supprimé aussitôt ; échecs purgés après 7 jours par `purge_task_results`. Le profil `taches` de docker-compose.yml (services `migrate`, `worker` et `scheduler`, réglages de développement et base `db` du fichier) sert au développement et aux essais ; le déploiement en production du travailleur et de la purge est fait au lot 8 | Validé (20 oct. 2026) |
| A3-05 | Notifications devenues fausses | Chaque transition supprime les notifications de la demande dont l'e-mail n'est pas encore parti (« Demande à valider », décision remplacée). Une annulation immédiate qui rend la demande de nouveau en attente prévient à nouveau les valideurs | Validé (20 oct. 2026) |
| A3-06 | Ouverture de campagne | Service sous verrou de toutes les campagnes de l'entreprise ; deux ouvertures simultanées donnent une seule campagne ouverte, l'autre reçoit « Une campagne est déjà ouverte. » | Validé (20 oct. 2026) |

## Préparation du lot 4 (21 oct. 2026)

Réponses aux questions Q1 à Q13 de la préparation du lot 4.

| N° | Sujet | Décision | Statut |
|---|---|---|---|
| L4-01 | Case du planning | État principal congé > télétravail > sur site ; vide le week-end ; libellé du jour férié ou de la fermeture ; « — » avant l'arrivée. Le repère « A » de l'astreinte reste visible le week-end et les jours non ouvrés (une astreinte de week-end se voit) | Validé (21 oct. 2026) |
| L4-02 | Jours fériés d'Alsace-Moselle | Réglage par site (« Services et sites » : Vendredi saint et 26 décembre) | Validé (21 oct. 2026) |
| L4-03 | Fermeture ajoutée après des demandes | Les demandes de télétravail du jour restent telles quelles ; les RH sont prévenus avec la liste des demandes concernées (notification et onglet Fermetures) ; le planning affiche la fermeture | Validé (21 oct. 2026) |
| L4-04 | Saisie des fermetures | Administrateur seul (onglet « Fermetures » de l'administration) ; les RH le consultent en lecture ; date passée refusée ; une fermeture par jour et par périmètre (entreprise ou site). Contrôles dans le service `add_closure`, sous verrou de l'entreprise (A3-02) ; une `IntegrityError` devient un message ; la liste des demandes envoyée aux RH est calculée sous le même verrou | Validé (21 oct. 2026) |
| L4-05 | iCalendar | Fichier .ics téléchargé, écrit sans dépendance (RFC 5545 : échappement, lignes de 75 octets) ; un événement par absence et par télétravail, coupé à la période demandée, « en attente » en TENTATIVE ; l'abonnement par URL est au lot 8 | Validé (21 oct. 2026) |
| L4-06 | PDF | WeasyPrint avec un récupérateur d'URL maison (`apps/core/pdf.py`) : seuls les polices et feuilles de style de Dianna et le logo de l'entreprise courante ; toute autre adresse refusée sans requête (file://, http(s)://, data:, adresses internes). Bibliothèques Pango et HarfBuzz ajoutées à l'image Docker | Validé (21 oct. 2026) |
| L4-07 | Grand effectif | 50 personnes par page dans les vues semaine et mois, filtres conservés, la personne connectée en tête de chaque page | Validé (21 oct. 2026) |
| L4-08 | Tableau de bord | Blocs des modules à venir (matériel, annonces, justificatifs, entretiens) masqués jusqu'à leur lot ; indicateurs disponibles à la place (salarié : prochains congés, sur site aujourd'hui ; manager : en congés aujourd'hui ; RH : demandes à valider, vœux de la campagne) | Validé (21 oct. 2026) |
| L4-09 | Exports RH | Bouton « Exporter » des RH et administrateurs dans chaque module : télétravail (récapitulatif du mois), astreintes (paie du mois), congés (synthèse de campagne) ; CSV ou Excel | Validé (21 oct. 2026) |
| L4-10 | Synthèse de campagne | Par service et par semaine de la période : vœux, absents et pourcentage de l'effectif en poste, alerte au-delà du seuil ; écran, CSV et Excel | Validé (21 oct. 2026) |
| L4-11 | Excel | Une feuille, en-têtes et colonnes d'identité figés, couleurs de la légende lues dans les jetons de `app.css` ; neutralisation des formules comme le CSV (toute cellule texte enregistrée comme texte) | Validé (21 oct. 2026) |
| L4-12 | Périmètre et journal des exports | Chaque export (planning, RH, synthèse) vérifie le périmètre côté serveur comme la vue ; un périmètre hors des choix de la personne est refusé (400). Journal d'audit avec période, format et périmètre, sans nom de personne | Validé (21 oct. 2026) |
| L4-13 | Colonnes de l'export du planning | Jours ouvrés (lundi à vendredi) de la période, comme le prototype ; jours fériés et fermetures avec leur libellé ; l'astreinte ajoutée au libellé de la case | Validé (21 oct. 2026) |
| L4-14 | Récapitulatif mensuel du télétravail | Toutes les personnes en poste (0 compris) et celles qui ont eu un télétravail validé dans le mois ; dates au format JJ/MM | Validé (21 oct. 2026) |
| L4-15 | Export paie des astreintes | Jours d'astreinte validés comptés dans le mois (une astreinte à cheval est coupée), interventions validées commencées dans le mois et leurs heures | Validé (21 oct. 2026) |
| L4-16 | Confidentialité du planning (minimisation) | Chacun voit tout ce qui le concerne. Le manager pour son équipe directe, les RH et l'administrateur voient le type exact d'absence (« Congés d'été », « Autre absence ») et les demandes en attente. Un collègue du périmètre ne voit que les demandes validées : « Absent » pour tout congé, quel que soit son type, « Télétravail » et l'astreinte. Règle appliquée à la vue, à l'aperçu et aux quatre formats d'export | Validé (21 oct. 2026) |
| L4-17 | Coût des exports | PDF limité à une page du planning (50 personnes) et à un mois ; au-delà : « Pour plus de personnes ou une période plus longue, utilisez l'export Excel. ». Limite de fréquence par personne sur tous les exports : `EXPORT_LIMIT` = 10 par `EXPORT_PERIOD` = 10 minutes (`apps/core/ratelimit.py`). Gunicorn : `--timeout 30`, `--graceful-timeout 30` (Dockerfile). Le plus gros PDF autorisé prend environ 2 s | Validé (21 oct. 2026, audit du lot 4) |
| L4-18 | Dates extrêmes | Dates acceptées du 1er janvier 2000 au 31 décembre 2100 (planning, exports) : hors bornes, le planning revient à aujourd'hui et un export donne « Choisissez une date entre 2000 et 2100. », jamais une erreur 500 | Validé (21 oct. 2026, audit du lot 4) |
| L4-19 | Vue mois pour un collègue | Lettre « Ab » pour « Absent » (« C » reste réservée au détail des congés, visible du manager, des RH et de soi) | Validé (21 oct. 2026) |
| L4-20 | Demande en attente d'un collègue | Invisible : la case affiche « Sur site » tant que la demande n'est pas validée | Validé (21 oct. 2026) |
| L4-21 | Limite de fréquence | Compteur commun à tous les exports d'une personne (planning, exports RH, synthèse) ; l'aperçu ne compte pas ; au-delà, page « Trop d'exports en peu de temps » (statut 429) ou message dans la modale, et rien n'est généré ni journalisé | Validé (21 oct. 2026) |
| L4-22 | « Page affichée » du PDF | Le bouton « Exporter » du planning transmet la page et le service affichés ; le PDF reprend ces 50 personnes. Sans page, un périmètre de plus de 50 personnes est refusé avec le message vers l'export Excel | Validé (21 oct. 2026) |
| L4-23 | Compteurs du jour | Pied du planning (« sur site aujourd'hui ») et bloc « Aujourd'hui » du tableau de bord : nombres seulement, calculés avec la même règle que les cases (L4-16, L4-20, fonction `sees_details`). Pour un collègue, seules les absences validées comptent ; le manager pour son équipe directe, les RH et l'administrateur comptent aussi les demandes en attente | Validé (21 oct. 2026) |

Nouvelles dépendances du lot 4 (accord du 21 oct. 2026) : `holidays` 0.107, `openpyxl` 3.1.5 (avec `et-xmlfile` 2.0.0), `weasyprint` 70.0 (avec `pydyf` 0.13.0, `tinycss2` 1.5.1, `cssselect2` 0.10.1, `tinyhtml5` 2.1.0, `fonttools` 4.67.0, `brotli` 1.2.0, `zopfli` 0.4.3, `pyphen` 0.18.1, `cffi` 2.1.1). Bornes dans `pyproject.toml` : `holidays<1`, `openpyxl<3.2`, `weasyprint<71` ; versions exactes dans `uv.lock`. Paquets système de l'image : `libpango-1.0-0`, `libpangoft2-1.0-0`, `libharfbuzz-subset0`.

## Préparation du lot 5 (21 oct. 2026)

Réponses aux questions Q1 à Q14 de la préparation du lot 5, et choix faits pendant le lot.

| N° | Sujet | Décision | Statut |
|---|---|---|---|
| L5-01 | Service des justificatifs | Servis seulement à une personne connectée qui a la permission (`transport.view` : le demandeur, les RH, l'administrateur), contrôlée à chaque téléchargement, jamais par lien signé. Réponse isolée : type exact, `X-Content-Type-Options: nosniff`, `Content-Security-Policy: sandbox`, pas de cache partagé. Nom d'origine jamais utilisé pour le stockage (`<company_id>/transport/<aléatoire>.<ext>`), échappé dans `Content-Disposition` (RFC 6266). Toute consultation par une autre personne que le demandeur est inscrite au journal, sans nom de fichier | Validé (21 oct. 2026) |
| L5-02 | Stockage S3 | Scaleway Object Storage (fr-par) avec `django-storages[s3]` et `boto3` ; un bucket par environnement, privé, chiffrement côté serveur, identifiants en variables d'environnement (`.env.example`). Développement et tests sur disque ; intégration continue sur MinIO avec chiffrement activé. Les images officielles de MinIO n'étant plus publiées, l'intégration continue utilise l'image `bitnamilegacy/minio:2025.7.23`, épinglée par son empreinte (`sha256:8935e75f…`) | Validé (22 oct. 2026), image MinIO comprise |
| L5-03 | PDF actifs | Seuls les PDF chiffrés sont refusés (`/Encrypt` cherché après décodage des échappements `#xx` des noms PDF : `/Encr#79pt` est reconnu) (« Ce PDF est protégé par un mot de passe. Enregistrez-le de nouveau sans protection. »), car ils ne peuvent pas être relus. Les autres PDF valides sont acceptés : la protection repose sur le service isolé du fichier (sandbox, nosniff, type exact), qui empêche l'exécution dans Dianna, plutôt que sur une analyse du contenu qui refuserait à tort des PDF ordinaires | Validé (21 oct. 2026) |
| L5-04 | Valideurs | Justificatifs de transport (M-06) et demandes de matériel (M-07) validés par les RH et administrateurs, sans étape manager (`hr_validated` dans le moteur commun). Justificatif d'un RH : validé par un autre RH ou l'administrateur ; sans personne d'autre, validation automatique tracée | Validé (21 oct. 2026) |
| L5-05 | Fichier d'une demande | Envoi retiré dans les 30 s : fichier supprimé. Refusé ou annulé : conservé pour l'historique jusqu'à la purge de conservation (3 ans, M-13, lot 8). Envoi interrompu par une erreur : fichier supprimé | Validé (21 oct. 2026) |
| L5-06 | Chevauchement | Un abonnement annuel actif bloque aussi les mensuels des mois qu'il couvre, et inversement (« Un justificatif de ce type couvre déjà {mois}. ») ; un titre unique reste toujours possible | Validé (21 oct. 2026) |
| L5-07 | Mois acceptés | Des 12 mois passés au mois prochain | Validé (21 oct. 2026) |
| L5-08 | Un seul détenteur | Garanti en base : une seule attribution ouverte par équipement (index unique partiel), cohérence état et détenteur (contrainte), une attribution au plus par demande ; services sous verrou de l'équipement ; deux attributions simultanées donnent une attribution et « Cet équipement est déjà attribué. » | Validé (21 oct. 2026) |
| L5-09 | Types et numéros de série | Liste fixe du prototype ; numéro de série normalisé par le service (Unicode NFKC, sans aucun espace ni espace insécable, en majuscules : « ＡＢ-123 » devient « AB-123 »), enregistré ainsi, unique dans l'entreprise par contrainte sur la valeur normalisée | Validé (21 oct. 2026) |
| L5-10 | Réparation | Depuis le stock, ou depuis un signalement sur un équipement attribué (le détenteur est conservé). Fin de réparation : « Rendre à {prénom} » s'il a un détenteur, sinon « Remettre en stock ». « Retirer du parc » seulement sans détenteur. « Envoyer en réparation » demande une confirmation et s'annule pendant 30 s depuis la notification visuelle : l'équipement reprend son état précédent ; l'historique garde « Envoyé en réparation » et ajoute « Envoi en réparation annulé », comme une attribution annulée ; un jeton d'annulation déjà utilisé est refusé | Validé (22 oct. 2026, annulation précisée le 23 oct.) |
| L5-11 | Archivage d'un détenteur | Non bloqué : alerte dans la confirmation, notification aux RH avec la liste ; le matériel reste attribué jusqu'à sa restitution | Validé (21 oct. 2026) |
| L5-12 | Relance des abonnements annuels | Notification et e-mail au salarié, une fois (`reminder_sent_at`, sous verrou), 15 jours avant la fin de validité. `manage.py enqueue_daily_tasks` met la tâche en file chaque jour (service `scheduler` en développement ; production au lot 8), le travailleur l'exécute | Validé (21 oct. 2026) |
| L5-13 | Export paie du transport | Justificatifs validés qui couvrent le mois ; abonnement annuel compté pour un douzième par mois ; remboursement estimé de 50 % (article L3261-2 du Code du travail) ; titre unique « Non concerné ». Le détail d'un justificatif affiche 50 % du montant payé | Validé (21 oct. 2026) |
| L5-14 | Attribution | Notification dans Dianna à la personne, sans e-mail ; annulable pendant 30 s depuis la notification visuelle (équipement remis en stock, attribution et notification supprimées) | Validé (21 oct. 2026) |
| L5-15 | Signalements | Faits par le détenteur seulement ; RH prévenus (administrateurs à défaut) ; clôture avec résolution obligatoire, l'auteur reçoit une notification | Validé (22 oct. 2026) |
| L5-17 | Stockage indisponible | Appels S3 avec une configuration botocore explicite : connexion 3 s, lecture 10 s, 2 essais au plus en mode « standard » (`S3_CONNECT_TIMEOUT`, `S3_READ_TIMEOUT`, `S3_MAX_ATTEMPTS` dans `apps/core/files.py`). Toute erreur de stockage est interceptée : dépôt d'un justificatif « Le stockage des fichiers est momentanément indisponible. Réessayez dans quelques minutes. » (503, rien n'est enregistré) ; téléchargement : page 503 avec le même message ; photos et logo : la vue n'appelle plus `exists()`, une panne donne une réponse 404 rapide et la page affiche les initiales ou masque le logo | Validé (21 oct. 2026, audit du lot 5) |
| L5-18 | Fichiers orphelins | Le nom du fichier est inscrit dans la liste de nettoyage avant toute écriture ; le fichier est écrit avant l'INSERT et supprimé si l'INSERT ou la suite échoue ; une DataError à l'INSERT donne un message. Même règle pour les photos et les logos (ancien fichier supprimé après la validation) et pour tout futur dépôt (CLAUDE.md) | Validé (21 oct. 2026, audit du lot 5) |
| L5-19 | Erreurs de contrainte | Chaque IntegrityError est traduite selon le nom de la contrainte en cause (moteur des demandes, matériel) ; une contrainte inconnue donne « La demande n'a pas pu être enregistrée : une valeur n'est pas acceptée. », jamais un message faux. La fenêtre de mois et les bornes du montant d'un justificatif sont aussi vérifiées par le service (A3-02) | Validé (21 oct. 2026, audit du lot 5) |
| L5-20 | Nombres décimaux | Montant d'un justificatif et durée d'une intervention : champ texte avec `inputmode="decimal"` (clavier numérique sur mobile), jamais `type="number"`, dont la saisie dépend de la langue du navigateur. Le serveur accepte la virgule et le point (« 2,15 » et « 2.15 » donnent 2,15), refuse tout autre format (« Saisissez un montant comme 84,10. », « Saisissez une durée comme 2,5. ») puis vérifie les bornes. Champ commun `apps/core/fields.DecimalTextField`, pour tout futur nombre décimal | Validé (22 oct. 2026, vérification élargie du lot 5) |
| L5-21 | Coupe-circuit du stockage | Par processus : après une panne du stockage, les appels suivants échouent aussitôt pendant 30 s (`CIRCUIT_BREAKER_SECONDS`, `apps/core/files.py`), sans contacter S3. Un annuaire de 12 photos avec S3 injoignable fait un seul appel au stockage (deux essais réseau, ceux de botocore) au lieu de 12 | Validé (22 oct. 2026, vérification élargie du lot 5) |
| L5-22 | Format des dates | Une seule fonction pour tout le projet : `apps/core/dates.format_date(valeur, style)`, filtre de gabarit `fr_date`. « 1er » pour le premier jour du mois (« 1er novembre 2026 »), jour abrégé suivi d'un point (« mer. 21 oct. ») dans les lignes de demandes et les en-têtes du planning | Validé (22 oct. 2026, vérification élargie du lot 5) |
| L5-23 | Largeur mobile | À 390 px, aucune page n'est plus large que l'écran : les tableaux larges défilent dans leur conteneur. Les conteneurs qui défilent (`.table-wrap`, `.plan`, `.tabs`, `.stepper`) sont en `position: relative`, sinon le texte `sr-only` (position absolue) des tableaux élargit la page. Un parcours Playwright vérifie les pages principales pour les 4 profils | Validé (22 oct. 2026, vérification élargie du lot 5) |
| L5-24 | Montants et heures dans Excel | Cellules enregistrées comme nombres, au format monétaire (`#,##0.00 "€"`, affiché « 1 234,56 € » dans un Excel français) ou décimal (`#,##0.00`), pour que les sommes fonctionnent : export paie du transport (montant payé, montant du mois, remboursement estimé) et des astreintes (heures). Seules les cellules texte passent par la neutralisation des formules. Le CSV garde le texte français (« 42,05 € »). Type `Number` de `apps/core/xlsx_export.py`, pour tout futur montant ou nombre d'heures | Validé (23 oct. 2026) |
| L5-25 | Exception : migrations fusionnées modifiées | Exception unique à la règle de CLAUDE.md « jamais modifiée une fois fusionnée » : `people/0002_employee_photo_and_history` et `core/0003_company_logo` (fusionnées avec les lots 2 et 4) ont été modifiées au lot 5. La modification se limite à l'argument `storage` des champs de fichier (`apps.core.files.get_private_storage` au lieu d'une instance figée qui contenait un chemin propre à une machine). Elle n'a aucun effet sur le schéma (aucune opération SQL), et `makemigrations --check` vérifie l'absence d'écart avec les réglages de développement et de production | Validé (23 oct. 2026) |
| L5-16 | En-tête HX-Trigger | JSON en ASCII (échappements `\uXXXX`) : un caractère hors Latin-1 (« € », « Œ ») était encodé par Django selon la RFC 2047 et rendait l'en-tête illisible pour htmx | Validé (technique) |

Nouvelles dépendances du lot 5 (accord du 21 oct. 2026) : `django-storages[s3]` 1.14.6 et `boto3` 1.43.116 (avec `botocore` 1.43.116, `s3transfer` 0.19.3, `jmespath` 1.1.0, `urllib3` 2.8.0). Bornes dans `pyproject.toml` : `django-storages[s3]>=1.14,<1.15`, `boto3>=1.35,<2`.

## Préparation et décisions du lot 6 (24 oct. 2026)

Réponses aux questions Q1 à Q11 de la préparation du lot 6, et choix faits pendant le lot.

| N° | Sujet | Décision | Statut |
|---|---|---|---|
| L6-01 | Résultats des questionnaires | Visibles seulement après la clôture, ou l'échéance passée, et à partir du seuil d'anonymat (5 réponses, L6-17). Pendant l'ouverture, seul le nombre de réponses s'affiche (« 4 réponses reçues · Les résultats seront visibles à la clôture »), pour aucun profil la liste de qui a répondu ou non. Évite qu'une différence entre deux consultations révèle une réponse. Une seule règle, `surveys.selectors.results_visible`, par laquelle passe `survey_results` (résultats, commentaires, réponses libres, tout futur filtre ou export). Si une relance est ajoutée, elle partira automatiquement aux non-répondants, sans que personne ne voie leurs noms. **Écart au prototype**, qui montre les résultats d'un questionnaire ouvert | Validé (24 oct. 2026) |
| L6-02 | Date des réponses | `SurveyResponse.submitted_on` supprimé : une réponse ne porte aucune date (avec une seule réponse un jour donné, elle la reliait au reçu) | Validé (24 oct. 2026) |
| L6-03 | Reçu et réponse | Créés dans la même transaction, sans clé commune : la réponse dans la transaction du service, le reçu dans une sous-transaction (contrainte unique, seconde réponse refusée). Le `xmin` du reçu vaut celui de la réponse + 1 : risque ajouté à L1-09. Répondre n'écrit ni journal, ni notification, ni tâche, ni log | Validé (24 oct. 2026, précisé le 25 oct.) |
| L6-04 | Public | Figé à la publication (`SurveyInvitation`) : droit de répondre, bandeau « à remplir », participation. « Tous les salariés » : personnes présentes (statut « Actif »), RH et administrateur compris ; « Managers » : au moins un collaborateur direct en poste ; « Arrivés depuis moins d'un an » : arrivée dans les 365 jours avant la publication | Validé (24 oct. 2026) |
| L6-05 | Public sous le seuil | Publication refusée, avant même la confirmation : « Le public compte moins de 5 personnes : les résultats ne pourraient jamais être affichés sans risque pour l'anonymat. ». Seuil fixe dans l'écran, contrainte en base ≥ 5 (L6-17) | Validé (24 oct. 2026, seuil porté à 5 le 25 oct.) |
| L6-06 | Échéance | Facultative. Après la date, le serveur refuse les réponses ; `enqueue_daily_tasks` clôt chaque jour les questionnaires échus (journal « clos automatiquement ») | Validé (24 oct. 2026) |
| L6-07 | Brouillon | « Modifier le brouillon » (titre, public, échéance, questions) tant qu'il n'est pas publié ; ensuite 404. **Écart au prototype**, qui ne le prévoit pas. Au moins une question notée, comme le formulaire du prototype | Validé (24 oct. 2026) |
| L6-08 | E-mail des annonces | Seulement à la publication d'une annonce épinglée (M-16). Modifier ou épingler ensuite n'envoie rien et ne notifie pas de nouveau | Validé (24 oct. 2026) |
| L6-09 | Annonce supprimée | Suppression logique (`deleted_at`), annulable 30 s ; contenu gardé jusqu'à la purge (lot 8). Les notifications restent ; leur lien mène à « Cette annonce a été supprimée. » (404) | Validé (24 oct. 2026) |
| L6-10 | Limites | Annonce : titre 120, message 15 à 5 000 caractères. Questionnaire : titre 120, 1 à 20 questions notées de 300 caractères, une question ouverte. Réponse : commentaire 1 000, réponse libre 2 000 | Validé (24 oct. 2026) |
| L6-11 | Résultats des managers | Ceux de toute l'entreprise (matrice), pas de résultats par service avant le lot 8 | Validé (24 oct. 2026) |
| L6-12 | Modèle sans horodatage | `TenantBase` (isolation sans `Timestamped`), réservée aux réponses anonymes (`SurveyResponse`, `Answer`) ; `TenantModel` = `TenantBase` + `Timestamped`, sans migration des modèles existants. Un test refuse tout autre modèle métier sans horodatage | Validé (technique) |
| L6-13 | Briques communes du lot 6 | Évolutions au lieu de variantes : `notifications.notify_many` (une insertion pour tout le public, entreprise revérifiée) ; `htmx.location` (HX-Location vers `#content`, la notification visuelle et son « Annuler » restent) ; `htmx.error_response`, `confirm_response`, `modal_form_response` ; `core.errors.ServiceError` ; `access.company_module_enabled` (tâches) ; filtre `plain_text` (texte échappé, liens détectés). L'existant n'est pas repris (dette technique, note du lot 6) | Validé (technique) |
| L6-14 | Annonces : public et lecture | Public : personnes présentes (« Actif »). Lectures « x sur y » : personnes présentes seulement ; visibles de l'auteur, des RH et de l'administrateur (`announcements.services.can_see_reads`). L'auteur a lu son annonce dès la publication | Validé (technique) |
| L6-15 | Démonstration | Arrivées de p13, p14, p22, p23 et p24 recalculées à 330, 300, 200, 160 et 120 jours avant le chargement : le public « Arrivés depuis moins d'un an » du questionnaire « Intégration » compte 5 personnes (seuil). « Intégration » est clos avec 3 réponses (résultats masqués), « Enquête télétravail 2025 » clos avec 18 réponses (résultats visibles). Le brouillon « Besoins de formation 2027 » a une question notée en plus de la question ouverte | Validé (technique, mis à jour le 25 oct.) |
| L6-16 | Qualité du code | ruff : complexité ≤ 10 (C90), 6 `return`, 12 branches, 8 arguments, 50 instructions (PLR0911 à PLR0915), plus B, SIM, RET, DJ, N, PTH. Seuil de 8 arguments (et non 6) : les services prennent des arguments nommés (`*, actor, request`). Seule exception : le gabarit `button` (un argument par attribut HTML). RUF100 signale tout `noqa` devenu inutile | Validé (technique) |
| L6-17 | Seuil d'anonymat à 5 | Public minimal de 5 personnes pour publier ; résultats, commentaires et réponses libres à partir de 5 réponses ; contrainte en base ≥ 5 (les questionnaires existants passent à 5 par migration). Raison : à 3, deux répondants qui comparent leurs réponses déduisent celles du troisième ; à 5, toute paire de complices laisse au moins trois réponses inconnues | Validé (25 oct. 2026, audit du lot 6) |
| L6-18 | Annonce supprimée et e-mails | La suppression retire les notifications dont l'e-mail n'est pas encore parti (`retract_unsent`, notifications rattachées à leur annonce) ; une annonce épinglée supprimée dans les 45 s n'envoie aucun e-mail. « Annuler » recrée les notifications manquantes ; un e-mail déjà parti n'est jamais renvoyé. La tâche d'envoi vérifie aussi que l'objet source existe toujours (registre `notifications.register_source` : demandes, annonces non supprimées) | Validé (25 oct. 2026, audit du lot 6) |
| L6-19 | Caractères invisibles | `apps/core/text.strip_unsafe_characters` retire les caractères de contrôle C0 et C1 (sauf tabulation et retour à la ligne ; le retour chariot est retiré) et les caractères de mise en forme bidirectionnelle (U+061C, U+200E, U+200F, U+202A à U+202E, U+2066 à U+2069), ainsi que les séparateurs de ligne et de paragraphe U+2028 et U+2029 (ajoutés le 26 oct.). Appliqué à tous les champs texte de tous les formulaires (branché sur `forms.CharField` au démarrage : formulaires du projet, ModelForm, allauth, administration ; jamais aux mots de passe) et aux valeurs d'un CSV importé | Validé (25 oct. 2026, audit du lot 6) |
| L6-20 | Actions des questionnaires | Une confirmation (publier, clore, supprimer, prolonger, modifier) ne s'ouvre que si l'action est possible ; sinon le message dit l'état réel (« Ce questionnaire est déjà clos. », « … déjà publié. », « … pas encore publié. »), jamais « a changé entre-temps ». Le bouton « Répondre » disparaît après l'échéance | Validé (25 oct. 2026, audit du lot 6) |
| L6-21 | Prolonger l'échéance | Action RH sur un questionnaire ouvert dont l'échéance n'est pas passée : nouvelle date à venir et postérieure à l'échéance actuelle ; inscrite au journal avec l'ancienne et la nouvelle date. Après l'échéance, plus de prolongation (« L'échéance est passée : le questionnaire ne peut plus être prolongé. ») : dès que les résultats ont pu être visibles, plus aucune réponse ne doit entrer, sinon la différence entre deux consultations révélerait les réponses d'une personne (L6-01). Un questionnaire échu est traité comme clos partout (statut affiché « Clos », filtre, réponses refusées, bouton « Répondre » absent, résultats selon le seuil), même avant que la tâche quotidienne change son statut | Validé (25 oct. 2026, corrigé le 26 oct.) |
| L6-22 | Commentaires des résultats | 5 commentaires (ou réponses libres) par question sur la page, puis « Afficher plus » par paquets de 20, chargés seulement si les résultats sont visibles (même règle `results_visible`) ; après « Afficher plus », le focus va sur le premier commentaire chargé (WCAG 2.4.3) | Validé (25 oct. 2026, audit du lot 6) |
| L6-23 | Course à minuit | `submit_answers` prend le verrou exclusif du questionnaire avant de lire la date ; `survey_results` et `more_written_answers` prennent un verrou partagé (`SELECT … FOR SHARE`, écrit en SQL car Django ne propose que `FOR UPDATE`). Une lecture des résultats attend qu'une réponse en cours soit validée ou refusée : aucune réponse ne peut entrer après une lecture des résultats. Test à deux connexions réelles | Validé (26 oct. 2026) |

Aucune nouvelle dépendance au lot 6.

## Reprise technique refacto-1 (26 oct. 2026)

| N° | Sujet | Décision | Statut |
|---|---|---|---|
| R1-01 | Vérification des types | mypy **2.4.0** et django-stubs **6.1.2** (avec django-stubs-ext 6.1.2), dépendances de développement (accord du 26 oct. 2026). `make typecheck`, bloquant dans l'intégration continue, sur tous les `services.py`, `selectors.py` et le moteur des demandes (`apps/approvals/workflow/`). Le reste du code est vérifié au lot 8. Bornes : `mypy>=2.4,<3`, `django-stubs[compatible-mypy]>=6.1,<6.2` | Validé (26 oct. 2026) |
| R1-02 | Navigation après une action | Une seule brique, `apps/core/htmx.after_action(request, toast, *, refresh, go_to, close_modal, page_form)`, et une seule règle. (1) Le résultat reste sur la page : notification visuelle et rechargement de la zone (`refresh` : événement de la zone ; `PAGE_CHANGED` recharge toute la zone `#content`, depuis l'adresse affichée dans le navigateur, même après un formulaire refusé). (2) Le résultat est une autre page : notification visuelle et HX-Location (`go_to`) ; le document n'est pas rechargé. (3) Un export garde HX-Redirect vers le fichier. Seule exception : l'activation d'un module recharge le document entier (`refresh=RELOAD_PAGE`), car le menu change aussi. Les formulaires en page complète (fiche de l'annuaire, paramètres de l'entreprise) passent par HTMX, erreurs en 422 sur place ; envoyés sans JavaScript (`page_form`), comme l'import CSV et « Tout marquer comme lu », ils reçoivent un message puis une redirection | Validé (26 oct. 2026) |

## Pour plus tard

- **Lot 7 :** un manager ne signe pas son propre entretien côté manager ; la note de suivi d'un salarié est limitée au type « Souhait ».
- **Lot 5 :** les justificatifs de transport sont servis seulement à un utilisateur connecté qui a la permission de les voir (contrôle à chaque téléchargement), pas par simple lien signé comme les photos et logos (A2-07).
- **Lot 8 :** le blocage après des échecs de connexion est indexé par adresse et par hôte.
- **Lot 8 :** limite de taille des envois au niveau du proxy (`client_max_body_size` ou équivalent) : Django ne limite pas la taille des fichiers reçus avant de les écrire sur disque.
- **Lot 8 :** génération des gros exports (PDF de plus de 50 personnes ou d'un mois, très gros Excel) en tâche d'arrière-plan avec un lien de téléchargement, si un client en a besoin (L4-17).
- **Lot 8 :** limites internes d'allauth (connexion, mot de passe oublié) : les remplacer par `apps/core/ratelimit.py` (compteur en base), comme les autres limites (L1-16).
- **Lot 8 :** création du compte Scaleway et des buckets (un par environnement) ; vérifier le mode de chiffrement côté serveur proposé (SSE-S3 ou équivalent) et l'activer (`S3_SERVER_SIDE_ENCRYPTION`) ; planifier `enqueue_daily_tasks` en production.
- **Lot 8 :** purge des justificatifs au-delà de leur durée de conservation (3 ans, M-13), fichiers compris.
- **Lot 8 :** analyse antivirus de chaque fichier au moment du dépôt, avant son enregistrement dans le stockage et en base (ClamAV ou équivalent, prévu « à confirmer » dans 02-architecture.md) : un fichier infecté ou non analysable est refusé avec un message ; non faite au lot 5, à décider avec l'hébergement (service, dépendance, délai de réponse).
- **Lot 8 :** avec un S3 qui ne répond pas (connexion acceptée puis aucune réponse), la première visite de chaque fenêtre de 30 s du coupe-circuit (L5-21) coûte 7 à 10 s avant le message, et chaque processus Gunicorn a son propre coupe-circuit. À revoir avec l'infrastructure réelle : coupe-circuit partagé entre processus, délais de connexion et de lecture.
- **Lot 8 :** anonymat des questionnaires en base (L1-09, L6-03) : réécriture groupée et périodique des réponses d'un questionnaire (une seule transaction pour toutes), pour effacer le lien par le numéro de transaction et l'ordre physique ; règle d'exploitation « aucun accès SQL direct à la base de production hors procédure tracée ».
- **Lot 8 :** relance des non-répondants d'un questionnaire, si elle est ajoutée : automatique, sans que personne ne voie les noms (L6-01).
- **Lot 8 :** purge des annonces supprimées (suppression logique, L6-09).
- **Lot 8 :** catalogue de traduction français (`locale/fr`) : sans lui, les pluriels suivent la règle anglaise (« 0 collaborateurs » au lieu de « 0 collaborateur »). Corrigé à la main dans les écrans du lot 6.
- **Lot 8 :** remplacer l'image `bitnamilegacy/minio` de l'intégration continue (plus maintenue) par un serveur compatible S3 encore maintenu.
- **Lot 8 :** abonnement iCalendar par URL : jeton personnel, révocable, limité aux droits de son propriétaire (L4-05).
- **Lot 8 :** déploiement en production du travailleur de tâches (`db_worker`) et de la purge quotidienne (`purge_task_results`) ; le profil `taches` de docker-compose.yml ne sert qu'au développement et aux essais (A3-04).
- **Lot 8 :** le message d'erreur du serveur d'envoi (SMTP) est gardé 7 jours dans les tâches en échec (il peut contenir l'adresse du destinataire) : à revoir avec la politique de conservation RGPD (M-13).
- **Lot 8 :** changement d'identifiant de connexion (T-09, L2-11), en revoyant le message « Cette adresse est déjà utilisée sur Dianna », qui indique à un administrateur qu'une adresse a un compte dans une autre entreprise.

## V2, à décider après le lot 8

Demandes reçues pendant les lots, hors du périmètre de la V1. Rien de ceci n'est affiché dans Dianna (règle 6).

- **Soldes de congés payés et de RTT** : acquisition, décompte à la validation, report d'une année sur l'autre.
- **Types d'absence** : maladie, enfant malade, événement familial…, avec leurs règles (justificatif, décompte, visibilité au planning).
- **Relances aux valideurs** : rappel d'une demande en attente depuis plusieurs jours.
- **Validation groupée** : valider ou refuser plusieurs demandes en une fois.
- **Export du parc de matériel** (CSV, Excel).
- **Duplication d'un questionnaire** : repartir d'un questionnaire existant pour une nouvelle édition.
- **Export des résultats d'un questionnaire** (direction, CSE), en respectant le seuil d'anonymat (`results_visible`).
- **Résultats visibles par les salariés** (synthèse partagée après la clôture).
- **Filtre des commentaires par note** dans les résultats.

## Métier : à confirmer

| ID | Sujet | Recommandation appliquée par défaut | Statut |
|---|---|---|---|
| M-01 | Quota de télétravail | Réglé par entreprise (2 jours par semaine par défaut), avec dérogation possible par salarié. Pas de délai de prévenance en V1 | À confirmer |
| M-02 | Validation du télétravail | Par le manager direct. Option par entreprise : validation automatique dans la limite du quota | À confirmer |
| M-03 | Congés estivaux | Vœux par campagne (période, date limite, seuil de conflit) gérée par les RH ; arbitrage du manager (statut « Validée par le manager », hachuré au planning), puis validation finale des RH si l'entreprise garde cette étape (`summer_leave_hr_step`, activée par défaut). Le type « Autre absence » est validé par le manager seul. Seuil d'alerte de conflit : plus de 30 % du service absent le même jour | À confirmer |
| M-04 | Autres absences | Gestion minimale (type, dates, statut) pour que le planning soit complet. Pas de soldes ni d'acquisition (V2) | À confirmer |
| M-05 | Astreintes | Déclaration par le salarié, validation par le manager, export mensuel pour la paie. Pas de calcul des compensations | À confirmer |
| M-06 | Transport | Le montant estimé remboursé est de 50 % du titre d'abonnement (règle légale pour les transports publics, à vérifier par la paie). Validation par les RH. Relance 15 jours avant la fin de validité | À confirmer |
| M-07 | Matériel | Demandes traitées par les RH (ou un gestionnaire Moyens généraux quand ce profil existera) | À confirmer |
| M-08 | Entretiens | Entretien individuel annuel en 4 étapes. Entretien professionnel tous les 2 ans avec bilan à 6 ans (3 critères). Les règles légales sont à faire valider par un juriste avant commercialisation | À confirmer |
| M-09 | Signature des entretiens | Signature simple dans l'application (horodatage et identité), pas de signature électronique qualifiée | À confirmer |
| M-10 | Anonymat des questionnaires | Les réponses sont stockées sans lien avec le répondant ; un reçu séparé empêche de répondre deux fois. Résultats masqués sous 5 réponses (L6-17) | À confirmer |
| M-11 | Suivi d'intervention | Un compte rendu par intervention et par mois, validé par le manager direct | À confirmer |
| M-12 | Absence du valideur | Les RH et l'administrateur peuvent agir sur toute demande, tout entretien et tout compte rendu de l'entreprise à la place du manager (bandeau « Vous agissez à la place de {manager} », trace au journal). Leur onglet « À valider » et leurs compteurs ne montrent que les éléments des personnes sans manager. **Personne sans manager :** ses demandes vont aux RH et administrateurs autres qu'elle-même ; s'il n'y en a aucun, la demande est validée automatiquement, avec la ligne de journal « validation automatique : aucun valideur disponible ». Délégation nominative au lot 8 | Validé (18 oct. 2026) |
| M-13 | Conservation des données | Justificatifs de transport : 3 ans. Entretiens : durée du contrat + 5 ans. Notes de suivi : idem. Journal d'audit : 1 an. Salarié parti : fiche archivée, données supprimées ou anonymisées à l'échéance | À confirmer (avis juridique) |
| M-14 | Facturation | Hors V1 : abonnements gérés manuellement. Stripe en V2 | À confirmer |
| M-15 | Import des salariés | Import CSV par l'administrateur, avec aperçu et rapport d'erreurs | À confirmer |
| M-16 | Notifications par e-mail | Envoi pour : demande à valider, décision, entretien lancé, compte rendu à valider, nouvelle annonce importante. Préférences par utilisateur au lot 8 | À confirmer |

## Écarts entre le cahier des charges et le prototype

Le prototype validé a élargi la V1 initiale. À trancher pour l'ordre de livraison :

- **Carrière et évaluations, Questionnaires, Suivi du matériel, Suivi d'intervention** étaient prévus en V1.1 ou V2 dans le cahier des charges ; ils figurent dans le prototype validé. Recommandation : les livrer aux lots 5 à 7, après le cœur présence et organisation.
- Le cahier des charges prévoit aussi un profil « gestionnaire de module » et un profil « lecteur » ; ils sont remplacés par les 4 profils (V-06) en attendant.
- **Plan de charge et Recrutement** restent hors V1 (page « Bientôt » dans le prototype).

Écarts volontaires au prototype décidés pendant les lots :

- Résultats d'un questionnaire visibles seulement après sa clôture (L6-01).
- « Modifier le brouillon » d'un questionnaire (L6-07).
- « Envoyer en réparation » avec confirmation et annulation (L5-10).
