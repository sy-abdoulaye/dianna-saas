# Note de livraison : lot 4, planning et exports

Date : 21 octobre 2026. Branche : `lot-4`.

## Ce qui est fait

**Jours fériés et fermetures (T-16, L3-12).**
- Jours fériés du paquet `holidays` (France). Un site peut avoir les jours fériés d'Alsace-Moselle (Vendredi saint, 26 décembre), réglés dans « Services et sites » (L4-02).
- Fermetures saisies par l'administrateur dans un nouvel onglet « Fermetures » : toute l'entreprise ou un site. Les RH consultent cet onglet en lecture (L4-04).
- Le télétravail est refusé un jour férié ou fermé, à l'envoi et lors d'une annulation immédiate. Les messages : « Le 25 décembre est un jour férié (Noël). », « L'entreprise est fermée le … », « Votre site est fermé le … ».
- Une fermeture ajoutée après des demandes de télétravail les laisse en place. Les RH reçoivent une notification avec la liste des demandes concernées, aussi visible dans l'onglet (L4-03).

**Planning (`/planning/`).**
- Vues semaine et mois, navigation (précédent, Aujourd'hui, suivant), filtres nom, service (RH et administrateurs) et site, légende.
- Calcul d'une case (L1-07, L4-01) :
  - congés, puis télétravail, sinon sur site ;
  - « en attente » hachuré ;
  - repère « A » de l'astreinte, y compris le week-end ;
  - libellé du jour férié ou de la fermeture ;
  - « — » avant l'arrivée.
- Clic sur une de ses journées « Sur site » à venir : modale de télétravail pré-remplie. Le planning se met à jour après l'envoi.
- Périmètre vérifié côté serveur : son service ; pour un manager, son service et son équipe directe ; pour les RH et administrateurs, toute l'entreprise. Un service passé dans l'URL ne montre jamais personne de plus.
- 50 personnes par page, la personne connectée en tête de chaque page (L4-07).
- Pied : nombre de personnes et nombre sur site aujourd'hui.

**Export du planning (`/planning/export/`).**
- Période (semaine en cours, semaine prochaine, mois en cours, période personnalisée de 3 mois au plus), périmètre selon le profil, format.
- Aperçu de 6 lignes sur 5 jours, puis téléchargement.
- Formats :
  - CSV : point-virgule, BOM ;
  - Excel : une feuille, en-têtes figés, couleurs de la légende, formules neutralisées ;
  - iCalendar : fichier .ics sans dépendance ;
  - PDF : A4 paysage, une page par semaine.
- Chaque export est inscrit au journal avec la période, le format et le périmètre, sans nom de personne (L4-12).

**PDF sans accès réseau (L4-06).** Le récupérateur d'URL de WeasyPrint (`apps/core/pdf.py`) n'accepte que nos polices, nos feuilles de style et le logo de l'entreprise courante. `file://`, `http(s)://`, `data:` et les adresses internes sont refusés sans requête. Des tests vérifient qu'aucune connexion réseau n'est tentée, même avec une balise `<img>` ou un `url()` placé dans un libellé.

**Exports RH (L3-08, L4-09).** Un bouton « Exporter » pour les RH et administrateurs dans chaque module, en CSV ou Excel :
- Télétravail : récapitulatif mensuel des jours validés par salarié.
- Astreintes : export paie du mois (jours d'astreinte, interventions, heures).
- Congés : synthèse de campagne. Elle a aussi son écran, ouvert depuis les campagnes : vœux, absents par service et par semaine, alertes au-delà du seuil (L4-10).

**Tableau de bord complet (L4-08).**
- Indicateurs par profil.
- « À traiter » mène à l'onglet « À valider », avec les mêmes compteurs que le menu.
- « Aujourd'hui » : répartition sur site, télétravail, congés, astreinte, avec le lien « Voir le planning ».
- « Mes dernières demandes ».
- Les blocs des modules à venir restent masqués. Un module désactivé n'apparaît dans aucun bloc.

**Liens « Voir le planning » (L3-18)** sur les trois modules de demandes, le bandeau de campagne, la synthèse et le tableau de bord. Ils sont masqués si le module Planning est désactivé.

**Démonstration.** Fermeture du site de Lyon le 24 décembre. Le télétravail de démonstration qui tomberait un jour férié est décalé au jour ouvré suivant.

## Performance

200 personnes sur un mois, mesuré sur la machine de développement après l'audit (budget 300 ms) :

| Mesure | Temps | Requêtes |
|---|---|---|
| Vue mois (page de 50) | 160 à 200 ms | constantes (29) |
| Export CSV du mois | environ 70 ms | constantes (16) |
| Export Excel du mois | 145 à 180 ms | constantes (16) |
| Calcul de la grille sans pagination (200 lignes) | environ 40 ms | constantes |

La règle de confidentialité (L4-16) avait ralenti la vue mois (environ 210 ms) et l'Excel (environ 250 ms). Deux optimisations ont rendu de la marge : la case du planning est rendue en ligne, sans inclusion de gabarit par case, et chaque cellule Excel reçoit un seul style nommé au lieu de trois affectations.

**PDF au maximum autorisé (L4-17) : 50 personnes sur un mois, 5 pages, 137 Kio.**

| Mesure | Résultat |
|---|---|
| Temps de la requête complète, machine de développement | 1,6 à 1,9 s |
| Temps du rendu, image Docker (HarfBuzz-Subset présent) | environ 1,7 s |
| Mémoire résidente réelle d'un processus qui ne fait que ce rendu (module resource, `ru_maxrss`, bibliothèques natives comprises) | 92 Mio avant le rendu, 146 Mio au maximum : +54 Mio (machine de développement ; 92 et 148 Mo dans l'image Docker) |

Ce qui est mesuré : le pic de mémoire résidente du processus, et non plus seulement les allocations Python (tracemalloc, environ 44 Mio). Le processus de mesure est séparé et lancé par un shell intermédiaire. En effet, le pic du processus de test est déjà atteint par la création de la base, et `ru_maxrss` survit au fork et à l'exec sous Linux. Tests : `apps/planning/tests/test_pdf_memory.py`, budgets de 5 s et de +200 Mio.

Les tests de performance s'exécutent dans un second passage de `make test`, sans mesure de couverture.

## Image Docker

| Image | Taille |
|---|---|
| `main` avant le lot 4 | 566 Mo |
| `lot-4` | 742 Mo (+176 Mo) |

Tailles mesurées par `docker image inspect`. Couches modifiées, d'après `docker history` (qui ne compte pas comme `inspect`, d'où un total différent) :
- bibliothèques système Pango et HarfBuzz : +18 Mo ;
- dépendances Python : +118 Mo (254 → 372 Mo), surtout `fonttools` et `holidays`, bytecode précompilé compris ;
- code et fichiers statiques : +3 Mo.

L'intégration continue vérifie que WeasyPrint produit un PDF dans l'image et affiche sa taille.

## Dépendances ajoutées (accord du 21 octobre 2026)

- `holidays` 0.107
- `openpyxl` 3.1.5
- `weasyprint` 70.0
- paquets système de l'image : `libpango-1.0-0`, `libpangoft2-1.0-0`, `libharfbuzz-subset0`

La liste des dépendances transitives est dans `00-decisions.md`.

## Corrections de l'audit du lot 4 (21 oct. 2026)

- **Coût des exports (L4-17).**
  - Le PDF est limité à une page du planning (50 personnes, la page affichée quand l'export part du planning) et à un mois. Au-delà : « Pour plus de personnes ou une période plus longue, utilisez l'export Excel. ».
  - Chaque personne a droit à 10 exports par tranche de 10 minutes, tous exports confondus (`apps/core/ratelimit.py`).
  - Gunicorn a un délai explicite : `--timeout 30` et `--graceful-timeout 30`.
- **Confidentialité du planning (L4-16).** Un collègue voit « Absent » pour tout congé, « Télétravail » et l'astreinte, et seulement ce qui est validé. Le manager pour son équipe directe, les RH et l'administrateur voient le type exact et les demandes en attente ; chacun voit tout de lui-même. La règle s'applique à la vue, à l'aperçu, au CSV, à l'Excel, à l'iCalendar et au PDF.
- **Dates extrêmes (L4-18).** Les dates vont de 2000 à 2100. Hors bornes, le planning revient à aujourd'hui et un export donne une erreur de formulaire, jamais une erreur 500.
- **iCalendar.** Les événements sont coupés à la période demandée.
- **Fermetures (A3-02).** La date passée et le doublon sont contrôlés dans `add_closure`, sous verrou de l'entreprise. Une `IntegrityError` devient un message. La liste envoyée aux RH est calculée sous le même verrou. Un test de concurrence à deux connexions le vérifie.
- Tests : `apps/planning/tests/test_audit.py` et `apps/administration/tests/test_closures.py`.

## Derniers points de la vérification (21 oct. 2026)

- **Compteurs du jour (L4-23).** Le pied « sur site aujourd'hui » et le bloc « Aujourd'hui » du tableau de bord appliquent la règle des cases, avec la même fonction `sees_details`. Un congé en attente d'un collègue ne change ni sa case ni les compteurs vus par un salarié ou par un manager qui n'est pas le sien.
- **Limite de fréquence en base (L1-16).**
  - `RateLimitCounter` est incrémenté en une seule requête PostgreSQL atomique. Il sert aux exports et à la vitrine. Les clés sont des empreintes HMAC, et les fenêtres expirées sont supprimées par `purge_task_results`.
  - Tests : 30 exports simultanés depuis des connexions réelles donnent 10 acceptés et 20 refusés ; 400 autres clés n'effacent pas un compteur.
- **Mémoire du PDF.** C'est maintenant la mémoire résidente réelle (module resource), voir « Performance ».
- **CLAUDE.md.** Deux règles ajoutées : une seule fonction de confidentialité, et toute limite de fréquence passe par `apps/core/ratelimit.py`.

## Tests

| Commande | Résultat |
|---|---|
| `make lint` | sans erreur |
| `make test` | 558 tests (couverture 96 %), puis 6 tests de performance |
| `make e2e` | 38 parcours, dont le parcours 1 depuis le planning, l'export CSV et le tableau de bord |
| `make check` | aucune alerte, dont `--deploy` |

Les dates des tests ne dépendent plus du jour d'exécution : `next_weekday` choisit une semaine sans jour férié.

## Critères d'acceptation (fiche 06)

| Critère | État |
|---|---|
| Télétravail validé plein, en attente hachuré, refusé absent | Fait |
| Le 25 décembre est vide et marqué férié | Fait |
| Un salarié ne voit pas les autres services, même en modifiant l'URL | Fait (vue et export) |
| Une période de 4 mois est refusée avec « La période est limitée à 3 mois par export. » | Fait |
| Le CSV s'ouvre correctement dans Excel (accents, séparateur) | Fait (BOM et point-virgule vérifiés) |

## Points à relire

- Décisions « À confirmer » :
  - L4-01 : repère « A » visible le week-end ;
  - L4-13 : colonnes de l'export, jours ouvrés seulement ;
  - L4-14 : récapitulatif du télétravail avec les personnes à 0 ;
  - L4-15 : calcul des jours d'astreinte à cheval sur deux mois ;
  - L4-19 à L4-23 : choix faits pendant l'audit (lettre « Ab », demandes en attente des collègues, compteur d'exports, page du PDF, bloc « Aujourd'hui »).
- L'abonnement iCalendar par URL reste au lot 8.
