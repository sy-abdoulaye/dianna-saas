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
| T-08 | Accès des entreprises | Sous-domaine par entreprise (`exemple.dianna.fr`). `dianna.fr` : page vitrine minimale avec « Accéder à mon espace » (saisie de l'e-mail, redirection vers le sous-domaine de l'entreprise) | Domaine unique et choix de l'entreprise à la connexion | Validé (18 oct. 2026) |
| T-09 | Comptes | `User` personnalisé, connexion par e-mail. `User.email` est l'identifiant de connexion, `Employee.email` le contact professionnel. À l'invitation, le compte est créé avec l'e-mail de la fiche ; modifier l'e-mail de la fiche ne change pas l'identifiant ; changer d'identifiant est une action séparée confirmée par e-mail. Un compte appartient à une seule entreprise en V1 : inviter une adresse déjà utilisée dans une autre entreprise est refusé (« Cette adresse est déjà utilisée sur Dianna. Utilisez une autre adresse ou contactez le support. ») | — | Validé (18 oct. 2026) |
| T-10 | Authentification | `django-allauth` 65.19.1 (compatibilité Django 6.1 vérifiée au début du lot 1), monté sous `/connexion/` : e-mail et mot de passe, réinitialisation, TOTP. Double authentification obligatoire pour RH, Administrateur et équipe Dianna, imposée par un **middleware maison** (inscription forcée à la première connexion et quand le profil passe à RH ou Admin) ; désactivable en développement par `DEMO_DISABLE_2FA` (refusé si `DEBUG = False`). SSO Google et Microsoft au lot 8 | Authentification Django native et code maison | Validé (18 oct. 2026) |
| T-11 | Tâches en arrière-plan | Cadre de tâches de Django 6 (`django.tasks`) avec le moteur base de données du paquet `django-tasks` : pas de Redis à opérer | Celery + Redis si le volume l'exige | À confirmer |
| T-12 | Fichiers | Stockage objet compatible S3 en France (Scaleway Object Storage ou OVHcloud), `django-storages`, bucket privé, URL signées de 5 minutes | Stockage disque local (déconseillé en production) | À confirmer |
| T-13 | E-mails | `django-anymail` avec un fournisseur européen (Brevo ou Scaleway Transactional Email) | — | À confirmer |
| T-14 | Hébergement | Conteneurs Docker chez un hébergeur français (Scaleway, OVHcloud ou Clever Cloud), PostgreSQL managé avec sauvegardes quotidiennes | — | À confirmer |
| T-15 | Exports | CSV (module `csv`, séparateur point-virgule, encodage UTF-8 avec BOM pour Excel), Excel (`openpyxl`), iCalendar (`icalendar`), PDF (`WeasyPrint`) | — | À confirmer |
| T-16 | Jours fériés | Paquet `holidays` (France), complété par les fermetures saisies par l'entreprise | — | À confirmer |
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
| L0-08 | Port PostgreSQL de développement | **5433** sur l'hôte (un PostgreSQL local occupe souvent 5432), réglable par `DB_PORT` dans `docker-compose.yml` | Validé (18 oct. 2026) |
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
| L1-09 | Anonymat des questionnaires | Risque résiduel accepté pour la V1 (rapprochement possible en base par l'ordre physique des lignes et la date du jour quand les réponses sont peu nombreuses). À documenter dans la fiche et à revoir au lot 8 | Validé (18 oct. 2026) |

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
| M-10 | Anonymat des questionnaires | Les réponses sont stockées sans lien avec le répondant ; un reçu séparé empêche de répondre deux fois. Résultats masqués sous 3 réponses | À confirmer |
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
