# Données de démonstration

La commande `python manage.py seed_demo` crée (ou recrée avec `--reset`) l'entreprise **Exemple SAS** (`slug = "exemple"`) avec les données du prototype. La source exacte est `reference/prototype-donnees-demo.js` : reprendre les mêmes personnes, demandes, équipements, annonces, questionnaires, entretiens et comptes rendus, en adaptant les dates relativement au jour du chargement (le prototype est figé au lundi 19 octobre 2026).

Elle crée aussi une seconde entreprise **Autre SA** (`slug = "autre"`) avec quelques salariés et demandes, pour vérifier l'isolation à l'œil.

## Comptes de démonstration

Mot de passe commun en développement uniquement : `demo-dianna-2026`. La commande refuse de s'exécuter si `DEBUG = False`. En développement, `DEMO_DISABLE_2FA = True` dispense les comptes RH et Admin de démonstration de la double authentification.

| Profil | Personne | E-mail |
|---|---|---|
| Salarié | Camille Durand, conseillère support, Lyon | camille.durand@exemple.fr |
| Manager | Louise Martin, responsable support (équipe de 6) | louise.martin@exemple.fr |
| RH | Hélène Faure, directrice des ressources humaines | helene.faure@exemple.fr |
| Administrateur | Marc Diallo, administrateur de la plateforme | marc.diallo@exemple.fr |
| Administrateur d'**Autre SA** | Nadia Berger, directrice générale (pour vérifier l'isolation) | nadia.berger@autre.fr |

Adresses en développement : vitrine http://localhost:8000, Exemple SAS http://exemple.localhost:8000, Autre SA http://autre.localhost:8000, administration éditeur http://admin.localhost:8000 (compte créé par `python manage.py createsuperuser`). Les autres salariés ont une fiche sans compte.

## Contenu

- 24 salariés répartis sur 3 sites (Lyon, Paris, Nantes) et 6 services (Louise Martin a 5 collaborateurs directs dans le prototype, l'« équipe de 6 » ci-dessus l'inclut) ; 4 managers (Louise Martin, Paul Lefèvre, Claire Dubois, Élodie Vidal) ; 1 arrivée prochaine ; 1 départ.
- Demandes de télétravail sur la semaine courante et la suivante, dont une en attente pour Camille et deux à valider pour Louise.
- Campagne « Été 2027 » ouverte, avec des vœux qui se chevauchent dans le service Support client (conflit visible).
- Astreintes et interventions, justificatifs de transport (un refusé, plusieurs en attente).
- 15 équipements (attribués, en stock, en réparation) et 3 demandes de matériel.
- 5 annonces (2 épinglées), 4 questionnaires (ouvert, ouvert avec moins de 3 réponses, clos, brouillon) avec commentaires sur les notes.
- 10 entretiens à toutes les étapes, fiches de suivi avec une note privée de Louise.
- 4 comptes rendus d'intervention : validé, brouillon, envoyé (à valider par Louise), complément demandé.

**Écarts volontaires avec le prototype :** le questionnaire « Retour sur l'intégration » n'a que 2 réponses (pour montrer les résultats masqués) ; l'annonce « Nouvelle politique de télétravail » ne mentionne pas de délai de déclaration (M-01).

Les justificatifs et photos de démonstration sont des fichiers générés (PDF d'une page, avatars à initiales), jamais de vraies pièces.
