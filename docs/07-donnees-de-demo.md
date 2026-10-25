# Données de démonstration

La commande `python manage.py seed_demo` crée (ou recrée avec `--reset`) l'entreprise **Exemple SAS** (`slug = "exemple"`) avec les données du prototype. La source exacte est `reference/prototype-donnees-demo.js` : reprendre les mêmes personnes, demandes, équipements, annonces, questionnaires, entretiens et comptes rendus, en adaptant les dates relativement au jour du chargement (le prototype est figé au lundi 19 octobre 2026).

Elle crée aussi une seconde entreprise **Autre SA** (`slug = "autre"`) avec quelques salariés et demandes, pour vérifier l'isolation à l'œil.

## Comptes de démonstration

Mot de passe commun en développement uniquement : `demo-dianna-2026`. La commande refuse de s'exécuter si `DEBUG = False`. En développement, `DEMO_DISABLE_2FA = True` dispense les comptes RH et Admin de démonstration de la double authentification.

| Profil | Personne | E-mail |
|---|---|---|
| Salarié | Camille Durand, conseillère support, Lyon | camille.durand@exemple.fr |
| Manager | Louise Martin, responsable support (5 collaborateurs directs) | louise.martin@exemple.fr |
| RH | Hélène Faure, directrice des ressources humaines | helene.faure@exemple.fr |
| Administrateur | Marc Diallo, administrateur de la plateforme | marc.diallo@exemple.fr |
| Administrateur d'**Autre SA** | Nadia Berger, directrice générale (pour vérifier l'isolation) | nadia.berger@autre.fr |

Adresses en développement : vitrine http://localhost:8000, Exemple SAS http://exemple.localhost:8000, Autre SA http://autre.localhost:8000, administration éditeur http://admin.localhost:8000 (compte créé par `python manage.py createsuperuser`). Les autres salariés ont une fiche sans compte.

## Contenu

- 24 salariés répartis sur 3 sites (Lyon, Paris, Nantes) et 6 services ; 4 managers (Louise Martin, Paul Lefèvre, Claire Dubois, Élodie Vidal) ; 1 arrivée prochaine ; 1 départ.
- Demandes de télétravail sur la semaine courante et la suivante, dont une en attente pour Camille et deux à valider pour Louise.
- Campagne « Été 2027 » ouverte, avec des vœux qui se chevauchent dans le service Support client (conflit visible).
- Astreintes et interventions ; justificatifs de transport (un refusé, plusieurs en attente) au lot 5.
- 15 équipements (attribués, en stock, en réparation) et 3 demandes de matériel.
- 5 annonces (2 épinglées), 4 questionnaires (ouvert, clos avec 3 réponses donc résultats masqués, clos avec résultats visibles, brouillon) avec commentaires sur les notes.
- Campagne d'entretiens « Campagne 2026 » (du 5 octobre au 18 décembre du prototype, dates décalées) ; les 4 compétences par défaut.
- 10 entretiens à toutes les étapes (lot 7) : Louise a quatre entretiens « à faire » (l'évaluation de Camille, deux entretiens à planifier, une signature) ; Camille attend l'évaluation de Louise. Fiches de suivi avec les notes du prototype, dont une note privée de Louise (visible par elle seule).
- 4 comptes rendus d'intervention : validé et brouillon (Camille), envoyé (Thomas Roux, à valider par Louise), complément demandé (Mehdi Benali).

**Écarts volontaires avec le prototype :** le questionnaire « Retour sur l'intégration » est clos avec 3 réponses, sous le seuil de 5 (résultats masqués) ; l'annonce « Nouvelle politique de télétravail » ne mentionne pas de délai de déclaration (M-01) ; les arrivées de Nina Lambert, Hugo Fabre, Samuel Perrin, Chloé Renard et Pierre Blanc sont recalculées à moins d'un an du chargement, pour que le public « Arrivés depuis moins d'un an » compte 5 personnes (L6-15) ; le brouillon « Besoins de formation 2027 » a une question notée ; les entretiens « professionnels » du prototype sont des entretiens de parcours professionnel au motif « périodique » (L7-01) ; les résultats des questionnaires ouverts ne sont pas affichés avant leur clôture (L6-01), seuls ceux de « Enquête télétravail 2025 » (clos, 18 réponses) le sont.

Les justificatifs et photos de démonstration sont des fichiers générés (PDF d'une page, avatars à initiales), jamais de vraies pièces.
