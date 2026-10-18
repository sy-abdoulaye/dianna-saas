# Dossier de développement Dianna

Ce dossier contient tout ce qu'il faut pour développer Dianna avec Claude Code. Il se dépose tel quel à la racine du dépôt Git (le fichier `CLAUDE.md` à la racine, le reste dans `docs/`).

## Ordre de lecture

| Fichier | Contenu | Quand le lire |
|---|---|---|
| `00-decisions.md` | Décisions validées et recommandations à confirmer (versions, bibliothèques, règles métier) | Au démarrage, puis à chaque doute |
| `01-produit.md` | Vision, périmètre, profils, glossaire | Au démarrage |
| `02-architecture.md` | Structure du projet, multi-entreprise, sécurité, HTMX, tests, déploiement | Lot 0 et lot 1, puis en référence |
| `03-modele-de-donnees.md` | Toutes les entités, champs, contraintes et index | Avant chaque migration |
| `04-permissions.md` | Matrice profil × module × action, avec périmètre | Avant chaque vue |
| `05-design-system.md` | Jetons, composants, modèles HTMX, accessibilité | Avant chaque template |
| `06-plan-de-livraison.md` | Lots, contenu, définition de terminé | Au début de chaque lot |
| `07-donnees-de-demo.md` | Jeu de données de démonstration | Lot 1, puis enrichi à chaque lot |
| `08-prompts-claude-code.md` | Le message à envoyer à Claude Code pour démarrer chaque lot | À chaque lot |
| `modules/*.md` | Une fiche par module : écrans, règles, états, notifications, critères d'acceptation | Avant de coder le module |
| `reference/prototype-dianna.html` | Prototype interactif validé, à ouvrir dans un navigateur | En permanence |
| `reference/prototype-donnees-demo.js` | Données fictives du prototype | Pour la commande `seed_demo` |
| `reference/tokens.css` | Jetons du design system au format Tailwind v4 | Lot 0 |

## Sources de vérité

En cas de contradiction : `00-decisions.md` l'emporte sur les fiches de modules, qui l'emportent sur le prototype. Le prototype l'emporte pour tout ce qui est visuel (mise en page, libellés, états, messages).

Le cahier des charges fonctionnel d'origine est disponible dans Claude Docs (« Cahier des charges fonctionnel — Application de gestion d'entreprise multi-tenant ») ; ce dossier en reprend les décisions à jour.
