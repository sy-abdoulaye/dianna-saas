# Dossier de développement Dianna : mode d'emploi

## Contenu

```
CLAUDE.md                      règles permanentes lues par Claude Code à chaque session
docs/README.md                 index du dossier
docs/00-decisions.md           décisions validées et recommandations « À confirmer »
docs/01-produit.md             vision, profils, périmètre
docs/02-architecture.md        structure, multi-entreprise, sécurité, HTMX, tests, déploiement
docs/03-modele-de-donnees.md   entités et champs
docs/04-permissions.md         matrice des droits
docs/05-design-system.md       jetons, composants, modales, notifications
docs/06-plan-de-livraison.md   9 lots et définition de terminé
docs/07-donnees-de-demo.md     entreprise de démonstration
docs/08-prompts-claude-code.md messages à envoyer à Claude Code, lot par lot
docs/modules/                  11 fiches de modules avec critères d'acceptation
docs/reference/                prototype interactif, données de démonstration, jetons Tailwind
```

## Pour démarrer

1. Relisez `docs/00-decisions.md` et changez le statut des lignes « À confirmer » que vous tranchez.
2. Créez un dépôt GitHub vide (par exemple `dianna`) et copiez-y ce dossier tel quel.
3. Ouvrez Claude Code dans ce dépôt et envoyez le premier message de `docs/08-prompts-claude-code.md`.
4. Avancez lot par lot. À la fin de chaque lot, vérifiez la démo avec les comptes de `docs/07-donnees-de-demo.md`.

## Développement local

Prérequis : `uv` (gestionnaire Python), Docker, `make`, `curl`. Python 3.13 est installé par uv. Pour les exports PDF (WeasyPrint), les bibliothèques Pango et HarfBuzz : sous Debian ou Ubuntu, `sudo apt install libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0` (déjà présentes dans l'image Docker).

```bash
make install     # dépendances, Chromium pour Playwright, .env, pre-commit, binaire Tailwind
make up          # PostgreSQL 18 (Docker, port 5434), CSS, migrations, serveur sur :8000
make css         # dans un second terminal : recompile la feuille de style à chaque modification
make worker      # dans un troisième terminal : travailleur des tâches (e-mails, invitations)
```

Adresses (les sous-domaines de `localhost` fonctionnent sans configuration dans Chrome et Firefox) :

| Adresse | Contenu |
|---|---|
| http://localhost:8000 | Vitrine « Accéder à mon espace » |
| http://exemple.localhost:8000 | Espace Exemple SAS (`make seed`, mot de passe `demo-dianna-2026`) |
| http://autre.localhost:8000 | Espace Autre SA (isolation) |
| http://admin.localhost:8000 | Administration éditeur (`uv run python manage.py createsuperuser`) |
| http://localhost:8000/dev/styleguide/ | Guide de style (développement uniquement) |

En développement, `DEMO_DISABLE_2FA=True` dispense les comptes RH et Admin de démonstration de la double authentification. Pour la tester : `DEMO_DISABLE_2FA=false make up`.

Déploiement (même image Docker pour le serveur et le travailleur) :

1. `python manage.py migrate`, puis `python manage.py createcachetable` (cache partagé des limites internes d'allauth ; les limites de Dianna sont comptées en base, table `core_ratelimitcounter`).
2. Serveur web : la commande par défaut de l'image (Gunicorn, 3 processus, délai de 30 s par requête : `--timeout 30`, `--graceful-timeout 30` ; le plus gros export autorisé prend environ 2 s).
3. Travailleur des tâches, dans un conteneur séparé : `python manage.py db_worker`. Sans lui, aucun e-mail ne part (invitations, mot de passe oublié, demandes).
4. Purge des résultats de tâches, une fois par jour : `python manage.py purge_task_results` (échecs de plus de 7 jours ; les tâches réussies sont supprimées dès leur fin). Les lignes de tâches ne contiennent ni lien ni texte d'e-mail en clair (A3-04). La même commande supprime les compteurs de limite de fréquence expirés.
   Pour le développement et les essais seulement : `docker compose --profile taches up -d` démarre la base `db`, applique les migrations (service `migrate`), puis le travailleur (`worker`) et la purge quotidienne (`scheduler`). Ces services utilisent les réglages de développement (`config.settings.dev` et ses clés publiques) et la base `db` de `docker-compose.yml` ; le `.env` créé par `make install` suffit et n'a pas à être modifié. En développement, les e-mails s'affichent dans le journal du travailleur : `docker compose logs -f worker`. Le déploiement en production du travailleur et de la purge est prévu au lot 8.
5. Variables obligatoires : `SECRET_KEY`, `MFA_ENCRYPTION_KEY`, `TASKS_ENCRYPTION_KEY`, `DATABASE_URL`, `ALLOWED_HOSTS`, `BASE_DOMAIN`.
Contrôles : `make lint`, `make test`, `make e2e`, `make check`. Liste complète : `make help`.

## À faire hors code avant la commercialisation

- Avis juridique : entretiens professionnels, durées de conservation, remboursement transport, registre des traitements, contrat de sous-traitance (DPA).
- Disponibilité du nom « Dianna » : nom de domaine et marque (INPI, EUIPO).
- Choix de l'hébergeur et du fournisseur d'e-mails.
- Audit de sécurité externe (isolation entre entreprises).
