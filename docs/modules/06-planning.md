# Planning et export du planning

## Planning

Route : `/planning/`. Actions : « Exporter », « Déclarer du télétravail ».

- **Barre de navigation :** précédent, Aujourd'hui, suivant, titre de la période (« Semaine du 19 oct. au 25 octobre 2026 » ou « octobre 2026 »), sélecteur Semaine / Mois.
- **Filtres :** nom ; service (RH, Admin) ; site ; légende (Sur site, Télétravail, Congés, Astreinte, En attente hachuré).
- **Grille :** une ligne par personne (l'utilisateur en premier, avec « (vous) »), une colonne par jour ; première colonne et en-tête figés ; colonne du jour en surbrillance ; week-ends grisés. Semaine : pastilles avec libellé. Mois : pastilles avec lettre (S, T, C, A) et libellé complet en info-bulle et pour les lecteurs d'écran.
- **Calcul d'une case :** congé > télétravail > astreinte > sur site (jour ouvré) ; vide le week-end, les jours fériés (libellé du jour férié) et les fermetures ; « — » avant l'arrivée. Source unique : `CalendarEvent`.
- **Interaction :** cliquer sur une de ses propres journées « Sur site » à venir ouvre la modale de télétravail pré-remplie.
- **Pied :** nombre de personnes, nombre sur site aujourd'hui.
- **Périmètre :** salarié et manager : leur service ; RH et Admin : toute l'entreprise.
- **Performance :** une requête pour les événements de la période (pas de requête par case) ; 200 personnes × 31 jours en moins de 300 ms côté serveur.

## Export du planning

Route : `/planning/export/`.

- **Champs :** Période (Semaine en cours, Semaine prochaine, Mois en cours, Période personnalisée avec dates), Périmètre (service ou entreprise selon le profil), Format.
- **Formats :** CSV (point-virgule, UTF-8 avec BOM), Excel (une feuille, en-têtes figés, couleurs de la légende), iCalendar (un événement par absence et télétravail, pour abonnement d'agenda : lot 8), PDF (A4 paysage, une page par semaine).
- **Contrôles :** fin ≥ début ; 3 mois au plus par export.
- **Comportement :** aperçu des 6 premières lignes et 5 premiers jours, puis téléchargement du fichier. Export journalisé.
- **Abonnement iCalendar (lot 8) :** URL personnelle secrète et révocable, limitée au périmètre de la personne.

## Critères d'acceptation

- Un télétravail validé apparaît en « Télétravail » plein ; en attente, hachuré ; refusé, n'apparaît pas.
- Le 25 décembre est vide et marqué férié.
- Un salarié ne voit pas les autres services, même en modifiant le filtre dans l'URL.
- Une période de 4 mois est refusée avec « La période est limitée à 3 mois par export. »
- Le CSV s'ouvre correctement dans Excel (accents, séparateur).
