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

Prérequis : `uv` (gestionnaire Python), Docker, `make`, `curl`. Python 3.13 est installé par uv.

```bash
make install     # dépendances, Chromium pour Playwright, .env, pre-commit, binaire Tailwind
make up          # PostgreSQL 18 (Docker, port 5433), CSS, migrations, serveur sur :8000
make css         # dans un second terminal : recompile la feuille de style à chaque modification
```

Le guide de style des composants est sur http://localhost:8000/dev/styleguide/ (développement uniquement).
Contrôles : `make lint`, `make test`, `make e2e`, `make check`. Liste complète : `make help`.

## À faire hors code avant la commercialisation

- Avis juridique : entretiens professionnels, durées de conservation, remboursement transport, registre des traitements, contrat de sous-traitance (DPA).
- Disponibilité du nom « Dianna » : nom de domaine et marque (INPI, EUIPO).
- Choix de l'hébergeur et du fournisseur d'e-mails.
- Audit de sécurité externe (isolation entre entreprises).
