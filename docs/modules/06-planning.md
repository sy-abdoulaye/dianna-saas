# Planning et export du planning

## Planning

Route : `/planning/`. Actions : « Exporter », « Déclarer du télétravail ».

- **Barre de navigation :** précédent, Aujourd'hui, suivant, titre de la période (« Semaine du 19 oct. au 25 octobre 2026 » ou « octobre 2026 »), sélecteur Semaine / Mois.
- **Filtres :** nom ; service (RH, Admin) ; site ; légende (Sur site, Télétravail, Congés, Astreinte, En attente hachuré).
- **Grille :** une ligne par personne (l'utilisateur en premier, avec « (vous) »), une colonne par jour ; première colonne et en-tête figés ; colonne du jour en surbrillance ; week-ends grisés. Semaine : pastilles avec libellé. Mois : pastilles avec lettre (S, T, C, A) et libellé complet en info-bulle et pour les lecteurs d'écran.
- **Calcul d'une case (L1-07, L4-01) :** état principal congé > télétravail > sur site (jour ouvré) ; l'astreinte se cumule et s'affiche par un repère « A » dans la case, y compris le week-end et les jours non ouvrés ; vide le week-end ; libellé du jour férié ou de la fermeture (« Noël (férié) », « Inventaire (fermeture) ») ; « — » avant l'arrivée. Source unique : `CalendarEvent`. Jours fériés : paquet `holidays`, Alsace-Moselle par site (L4-02) ; fermetures saisies dans l'administration (L4-04).
- **Confidentialité (L4-16) :** chacun voit tout ce qui le concerne ; le manager pour son équipe directe, les RH et l'administrateur voient le type exact d'absence (« Congés d'été », « Autre absence ») et les demandes en attente ; un collègue du périmètre ne voit que les demandes validées, « Absent » pour tout congé (lettre « Ab » en vue mois), « Télétravail » et l'astreinte. Même règle pour l'aperçu et les quatre formats d'export (voir `04-permissions.md`).
- **Dates (L4-18) :** de 2000 à 2100 ; une date hors bornes dans l'URL ramène à aujourd'hui.
- **Interaction :** cliquer sur une de ses propres journées « Sur site » à venir ouvre la modale de télétravail pré-remplie.
- **Pied :** nombre de personnes, nombre sur site aujourd'hui, calculé avec la règle de confidentialité (L4-23 : un congé ou un télétravail en attente d'un collègue ne compte pas, sauf pour son manager direct, les RH et l'administrateur) ; lien « Fermetures et jours fériés » pour les RH et administrateurs.
- **Grand effectif (L4-07) :** 50 personnes par page dans les deux vues, filtres conservés, la personne connectée en tête de chaque page.
- **Périmètre :** salarié : son service ; manager (personne qui a des collaborateurs directs) : son service plus les membres de son équipe rattachés à d'autres services (L1-06) ; RH et Admin : toute l'entreprise.
- **Performance :** une requête pour les événements de la période (pas de requête par case) ; 200 personnes × 31 jours en moins de 300 ms côté serveur.

## Export du planning

Route : `/planning/export/`.

- **Champs :** Période (Semaine en cours, Semaine prochaine, Mois en cours, Période personnalisée avec dates), Périmètre (service ou entreprise selon le profil), Format.
- **Formats :** CSV (point-virgule, UTF-8 avec BOM), Excel (une feuille, en-têtes et colonnes d'identité figés, couleurs de la légende, formules neutralisées), iCalendar (fichier .ics : un événement par absence et télétravail, « en attente » marqué provisoire ; abonnement d'agenda au lot 8), PDF (A4 paysage, une page par semaine, lundi à vendredi). Colonnes : jours ouvrés de la période (L4-13).
- **Contrôles :** fin ≥ début ; 3 mois au plus par export ; dates de 2000 à 2100 (« Choisissez une date entre 2000 et 2100. ») ; PDF : un mois et une page du planning (50 personnes) au plus, la page affichée quand l'export part du planning ; au-delà : « Pour plus de personnes ou une période plus longue, utilisez l'export Excel. » (L4-17).
- **Fréquence (L4-17) :** 10 exports par personne et par tranche de 10 minutes, tous exports confondus (planning, exports RH, synthèse) ; au-delà, « Vous avez fait 10 exports en moins de 10 minutes. Réessayez dans quelques minutes. ».
- **iCalendar :** événements coupés à la période demandée.
- **Comportement :** « Générer l'export » affiche l'aperçu des 6 premières lignes et 5 premiers jours, puis « Télécharger le fichier ». Export journalisé avec la période, le format et le périmètre, sans nom de personne (L4-12). Le périmètre est vérifié côté serveur comme dans la vue.
- **Abonnement iCalendar (lot 8) :** URL personnelle secrète et révocable, limitée au périmètre de la personne.

## Critères d'acceptation

- Un télétravail validé apparaît en « Télétravail » plein ; en attente, hachuré ; refusé, n'apparaît pas.
- Le 25 décembre est vide et marqué férié.
- Un salarié ne voit pas les autres services, même en modifiant le filtre dans l'URL.
- Une période de 4 mois est refusée avec « La période est limitée à 3 mois par export. »
- Le CSV s'ouvre correctement dans Excel (accents, séparateur).
