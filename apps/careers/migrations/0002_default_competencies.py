"""Les 4 compétences par défaut (docs/03-modele-de-donnees.md) pour les entreprises déjà
créées ; les nouvelles les reçoivent à la création (core.services.create_company)."""

from django.db import migrations

DEFAULTS = (
    ("Relation client", "Écoute, clarté des réponses"),
    ("Autonomie", "Initiative, organisation"),
    ("Travail en équipe", "Partage, entraide"),
    ("Maîtrise des outils", "Outils et méthodes du poste"),
)


def create_defaults(apps, schema_editor):
    Company = apps.get_model("core", "Company")
    Competency = apps.get_model("careers", "Competency")
    for company in Company.objects.all():
        if Competency.objects.filter(company=company).exists():
            continue
        Competency.objects.bulk_create(
            Competency(company=company, name=name, description=description, order=index)
            for index, (name, description) in enumerate(DEFAULTS, 1)
        )


class Migration(migrations.Migration):
    dependencies = [("careers", "0001_initial"), ("core", "0007_company_career_intervals")]

    operations = [migrations.RunPython(create_defaults, migrations.RunPython.noop)]
