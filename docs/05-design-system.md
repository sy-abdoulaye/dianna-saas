# Design system

La référence visuelle est le prototype (`reference/prototype-dianna.html`) et le canevas de design « Dianna — Design system » dans Claude. Les jetons prêts à l'emploi sont dans `reference/tokens.css` (vérifié avec Tailwind CSS 4.3).

## Identité

- **Nom :** Dianna. **Symbole :** un D construit dans une grille 3 × 3 (six cellules pleines, trois atténuées), coins arrondis. Le SVG est dans le prototype (symbole `#mark`).
- **Polices :** Schibsted Grotesk (titres, logo), IBM Plex Sans (interface), IBM Plex Mono (identifiants, numéros de série, libellés en capitales). Auto-hébergées (T-20).
- **Icônes :** Lucide (trait 1,5 px, extrémités arrondies), sprite SVG, tailles 16, 20 et 24 px. Toujours accompagnées d'un libellé, sauf actions universelles avec `aria-label`.

## Couleurs

Toujours utiliser les **rôles** (classes Tailwind générées depuis les variables), jamais les codes hexadécimaux.

| Rôle | Usage | Classe |
|---|---|---|
| app | fond de l'application | `bg-app` |
| surface, raised, subtle | cartes ; menus et modales ; zones secondaires | `bg-surface`, `bg-raised`, `bg-subtle` |
| field | fond des champs | `bg-field` |
| line, line-strong, btn-line | bordures : séparateurs ; champs ; boutons secondaires | `border-line`… |
| title, ink, ink-2, ink-3 | titres ; texte ; texte secondaire ; texte discret | `text-title`… |
| brand, brand-hover | action principale | `bg-brand` |
| link | liens et boutons fantômes | `text-link` |
| sel-bg, sel-ink | élément sélectionné (menu, onglet) | |
| focus, ring | anneau de focus, halo d'étape courante | |
| ok, warn, err, info (bg / ink) | statuts : succès, attente, erreur, information | `bg-ok-bg text-ok-ink`… |
| site, tel, cng, ast (bg / ink) | planning : sur site, télétravail, congés, astreinte | |
| av (bg / ink) | avatars à initiales | |

Les contrastes texte/fond respectent WCAG 2.2 AA dans les deux thèmes. Une couleur sémantique ne porte jamais l'information seule : toujours un libellé et, pour les statuts, un point de couleur.

**Thème.** Le script en tête de page lit la préférence (`localStorage`, puis `prefers-color-scheme`) et pose `data-theme="light"` ou `"dark"` sur `<html>` avant l'affichage, pour éviter le flash. Le choix « Clair / Sombre / Système » est dans le menu utilisateur et enregistré dans `User.theme` (copié en `localStorage` pour l'affichage immédiat).

## Typographie

| Niveau | Police | Taille / interligne | Graisse |
|---|---|---|---|
| Titre de page (h1) | Schibsted Grotesk | 32/40 (26/34 sur mobile) | 700 |
| Titre de section (h2) | Schibsted Grotesk | 18/28 | 600 |
| Sous-titre (h3) | Schibsted Grotesk | 16/24 | 600 |
| Texte | IBM Plex Sans | 14/20 | 400 |
| Libellé de champ | IBM Plex Sans | 14/20 | 500 |
| Aide, méta | IBM Plex Sans | 12/16 ou 13/20 | 400 |
| Capitales (en-têtes de tableau, groupes du menu) | IBM Plex Mono | 12/16, espacement 0,04 à 0,06 em | 500 |

Chiffres alignés (`tabular-nums`) dans les tableaux et indicateurs.

## Espacements, rayons, ombres

- Grille de 4 px. Espaces courants : 8, 12, 16, 24 px. Marge de page 24 px (16 px sur mobile).
- Rayons : 6 (petits), 8 (boutons, champs), 12 (cartes), 16 (notifications), 20 (modales).
- Hauteurs : boutons et champs 40 px (32 px pour les petits, 48 à 52 px dans les modales), ligne de tableau 56 px.
- Coque (`layouts/app.html`, L7-21, L7-22) : hauteur d'écran déclarée une seule fois (`.app`, 100dvh) ; le document ne défile jamais. En-tête fixe sur toute la largeur (hamburger, logo, recherche, notifications, avatar) ; dessous, le menu latéral sur toute la hauteur, sans défilement interne, et la zone principale (`.main`), seul conteneur à défilement vertical, positionnée pour contenir les éléments en position absolue. Seuls les tableaux et les barres d'onglets défilent horizontalement, dans leur conteneur. Contrôle automatique : `tests/e2e/test_layout.py`.
- Largeur du contenu : un seul réglage sur `.app` (`--page-max` 1 600 px centrée, `--page-pad` 16 px sur mobile, 24 px, puis 32 px à partir de 1 440 px). Les pages ne fixent pas leur propre largeur, sauf les formulaires de l'administration (largeur de lecture).
- Menu latéral : 264 px, sans défilement interne ; entrées resserrées sur les écrans peu hauts, carte de la personne masquée sous 760 px de haut. À partir de 1 024 px, le bouton ☰ le replie en **rail d'icônes** de 72 px (libellés lus par les lecteurs d'écran, infobulle au survol) ou le déplie ; état mémorisé dans le navigateur et appliqué avant l'affichage. **Écart au prototype**, qui n'a pas de rail (L7-22). Sur mobile, le menu est masqué : tiroir par-dessus le contenu avec un voile, fermé par le voile, Échap, un lien ou un changement de page ; le focus y reste et revient au bouton.
- Recherche de l'en-tête : menu déplié, elle commence au bord droit du menu, à la marge du contenu ; menu replié, après le logo et le nom, à la même marge ; sur mobile, elle prend la largeur restante.

## Composants communs

Chaque composant est un template d'inclusion dans `templates/components/` (ou une balise d'inclusion). Les noms ci-dessous sont à respecter.

| Composant | Fichier | Notes |
|---|---|---|
| Bouton | `button.html` | variantes primary, secondary, ghost, danger, icon ; taille sm ; état de chargement (spinner, désactivé) |
| Badge de statut | `status_badge.html` | point + libellé ; correspondance statut → couleur centralisée dans `core/status.py` |
| Champ de formulaire | `field.html` | libellé, étoile si obligatoire (`required_mark` : obligatoire à l'envoi seulement), aide, message d'erreur lié (`aria-describedby`), `aria-invalid`, texte après le champ (`suffix`, « % ») |
| Blocs répétables | `repeatable.html`, `repeatable_row.html` | blocs numérotés (« Travail réalisé 2 »), « Retirer » annulable, « Ajouter » sans recharger ni vider les autres blocs (lot 7) |
| Résumé d'erreurs | `form_errors.html` | bandeau rouge en tête de formulaire : « N informations sont à corriger » |
| Zone de fichier | `file_drop.html` | bordure pointillée, nom du fichier choisi, état d'erreur |
| Sélecteur segmenté | `segmented.html` | radios stylés (Liste/Cartes, Semaine/Mois, Oui/Non) |
| Note de 1 à N | `rating.html` | radios ronds 40 px |
| Tableau | `table.html` | en-tête en capitales Mono, ligne 56 px, défilement horizontal sur mobile |
| Barre de filtres | `filters.html` | recherche + listes déroulantes + « Réinitialiser », formulaire HTMX |
| Pagination | `pagination.html` | « 1 à 8 sur 24 », précédent/suivant, numéros, ellipses |
| Onglets | `tabs.html` | compteur optionnel |
| Carte indicateur | `kpi.html` | libellé, valeur, barre de progression optionnelle |
| État vide | `empty_state.html` | icône dans un carré teinté, titre, phrase, action |
| Squelette de chargement | `skeleton.html` | |
| Étapes | `stepper.html` | terminé, en cours (halo), à venir |
| Fenêtre modale | `modal.html` | voir ci-dessous |
| Confirmation | `confirm.html` | icône verte (action normale) ou rouge (action destructive), deux boutons de même largeur |
| Notification visuelle | `toast.html` | voir ci-dessous |
| Bandeau | `banner.html` | info, warn, err, ok |
| Erreur serveur | `server_error.html` | bandeau inséré dans la modale ou le formulaire : « Le serveur n'a pas répondu. Vos saisies sont conservées, vous pouvez réessayer. » |
| Avatar | `avatar.html` | photo ou initiales |
| Page d'accès refusé, introuvable, module désactivé | `pages/403.html`, `404.html`, `module_disabled.html` | |

### Fenêtre modale

D'après la capture validée : rayon 20 px ; en-tête avec une **icône dans un carré teinté de 48 px** (couleur `link` sur `sel-bg`, ou `err` pour une action destructive) et un titre de 24 px ; champs de 48 px de haut ; encadré « Mode démonstration » remplacé en production par une aide utile ou supprimé ; **boutons de pied de même largeur** (grille), « Annuler » secondaire à gauche, action principale à droite avec icône ; sur mobile, boutons empilés en pleine largeur. Fermeture par Échap, par le fond et par la croix ; focus piégé dans la modale et rendu au déclencheur.

Utiliser une modale pour les formulaires courts (demandes, notes, refus, attribution). Utiliser une page complète pour les formulaires longs (fiche salarié, entretien, compte rendu d'intervention).

### Notification visuelle

D'après la capture validée : carte blanche (ou `raised` en sombre), rayon 16 px, ombre portée ; **pastille ronde de 36 px** teintée selon le type (succès `ok`, information `info`, erreur `err`, avertissement `warn`) ; titre 16 px en gras ; message 14 px où le nom de la personne est en gras ; ligne d'actions : lien principal en couleur `link` (ex. « Voir l'entretien ») et « Annuler » en `ink-3` qui annule réellement l'action. Durée : 5 s, 8 s s'il y a une action, pause au survol ; 3 notifications au maximum.

## Accessibilité

- Lien d'évitement « Aller au contenu ».
- Repères `header`, `nav`, `main` ; un seul `h1` par page.
- Tableaux : `caption` (masquée visuellement), `th scope`.
- Messages d'erreur : texte explicite qui dit quoi corriger, jamais seulement la couleur.
- Zones mises à jour par HTMX : `aria-live="polite"` sur les résultats et les notifications.
- Cibles tactiles ≥ 44 px sur mobile.
- Contrôle automatique axe-core sur les pages principales (lot 8) et vérification clavier à chaque lot.

## Libellés

Reprendre les libellés du prototype mot pour mot. Quelques règles :
- Boutons à l'infinitif qui disent ce qui se passe : « Envoyer la demande », « Valider », « Demander un complément ».
- Confirmation après l'action : « Demande envoyée », « Compte rendu validé ».
- Erreurs : ce qui ne va pas et comment corriger (« Vous avez déjà 2 jours de télétravail la semaine du 26 oct. (maximum 2). »).
- Ne jamais affirmer qu'un e-mail a été envoyé si ce n'est pas le cas.
