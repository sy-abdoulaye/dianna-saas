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
| T-01 | Version de Python | 3.13 | 3.14 si toutes les dépendances la supportent | À confirmer |
| T-02 | Version de Django | 6.1 pour démarrer, puis passage à **6.2 LTS** (prévue en avril 2027) avant la mise en production | 5.2 LTS (sécurité jusqu'en avril 2028), plus conservatrice mais sans les fragments de templates ni la CSP intégrés | À confirmer |
| T-03 | PostgreSQL | 18 (version stable actuelle ; la 19 est en release candidate) | 17 si l'hébergeur ne propose pas encore la 18 | À confirmer |
| T-04 | Tailwind CSS | v4, outil autonome (binaire), via le paquet `django-tailwind-cli` ou un script `make css` | npm + Tailwind CLI si une chaîne Node existe déjà | À confirmer |
| T-05 | HTMX | **2.x** avec `django-htmx`. La 4.0 (sortie le 28 août 2026) change l'héritage des attributs et les noms d'événements ; on migrera plus tard | 4.0 directement | À confirmer |
| T-06 | Fragments HTMX | Fragments de templates intégrés à Django 6 (`{% partialdef %}`) ; sinon fichiers dans `partials/` | `django-template-partials` | À confirmer |
| T-07 | Architecture multi-entreprise | Une base, un schéma, colonne `company_id` sur chaque table métier, gestionnaire filtrant automatiquement, entreprise résolue par le middleware. Défense en profondeur par Row Level Security PostgreSQL au lot 8 | Un schéma par entreprise (`django-tenants`) : isolation plus forte, mais migrations et opérations plus lourdes | À confirmer |
| T-08 | Accès des entreprises | Sous-domaine par entreprise (`exemple.dianna.fr`) | Domaine unique et choix de l'entreprise à la connexion | À confirmer |
| T-09 | Comptes | `User` personnalisé, connexion par e-mail. Un compte appartient à une seule entreprise en V1 (hypothèse H8 du cahier des charges), mais le modèle `Employee` sépare l'identité de connexion de la fiche RH pour permettre le multi-entreprise plus tard | — | À confirmer |
| T-10 | Authentification | `django-allauth` : e-mail et mot de passe, réinitialisation, double authentification (TOTP) obligatoire pour RH et Administrateur : inscription imposée à la première connexion et quand un profil passe à RH ou Admin ; désactivable en développement par le réglage `DEMO_DISABLE_2FA` (refusé si `DEBUG = False`). SSO Google et Microsoft au lot 8 | Authentification Django native et code maison | À confirmer |
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
| T-22 | Super-administration éditeur | Interface d'administration Django réservée à l'équipe Dianna (création des entreprises, activation des modules). Aucun accès aux données métier d'une entreprise sans accès support tracé | Back-office dédié plus tard | À confirmer |

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
| M-12 | Absence du valideur | Les RH et l'administrateur peuvent agir sur toute demande, tout entretien et tout compte rendu de l'entreprise à la place du manager (bandeau d'avertissement « Vous agissez à la place de {manager} », trace au journal). Leur onglet « À valider » et leurs compteurs ne montrent que les éléments des personnes sans manager. Délégation nominative au lot 8 | À confirmer |
| M-13 | Conservation des données | Justificatifs de transport : 3 ans. Entretiens : durée du contrat + 5 ans. Notes de suivi : idem. Journal d'audit : 1 an. Salarié parti : fiche archivée, données supprimées ou anonymisées à l'échéance | À confirmer (avis juridique) |
| M-14 | Facturation | Hors V1 : abonnements gérés manuellement. Stripe en V2 | À confirmer |
| M-15 | Import des salariés | Import CSV par l'administrateur, avec aperçu et rapport d'erreurs | À confirmer |
| M-16 | Notifications par e-mail | Envoi pour : demande à valider, décision, entretien lancé, compte rendu à valider, nouvelle annonce importante. Préférences par utilisateur au lot 8 | À confirmer |

## Écarts entre le cahier des charges et le prototype

Le prototype validé a élargi la V1 initiale. À trancher pour l'ordre de livraison :

- **Carrière et évaluations, Questionnaires, Suivi du matériel, Suivi d'intervention** étaient prévus en V1.1 ou V2 dans le cahier des charges ; ils figurent dans le prototype validé. Recommandation : les livrer aux lots 5 à 7, après le cœur présence et organisation.
- Le cahier des charges prévoit aussi un profil « gestionnaire de module » et un profil « lecteur » ; ils sont remplacés par les 4 profils (V-06) en attendant.
- **Plan de charge et Recrutement** restent hors V1 (page « Bientôt » dans le prototype).
