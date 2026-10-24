"""Le plus gros PDF autorisé (L4-17) : 50 personnes sur un mois, temps et mémoire réelle.

- Temps : la requête complète (vue, données, rendu), dans le processus de test.
- Mémoire : mémoire résidente réelle (module resource, `ru_maxrss`, bibliothèques natives
  Pango et HarfBuzz comprises), mesurée dans un processus Python séparé qui ne fait que ce
  rendu. Dans le processus de test, le pic est déjà atteint par la création de la base et ne
  redescend jamais : il ne dirait rien du PDF. Sous Linux, `ru_maxrss` survit au fork et à
  l'exec : le processus de mesure est lancé par un petit shell intermédiaire (petit-fils du
  processus de test), pour partir d'une empreinte vierge."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from django.conf import settings

from apps.planning.tests.test_performance import MONTH_EXPORT, median_seconds, populate

pytestmark = [pytest.mark.django_db, pytest.mark.perf]
PDF_BUDGET_SECONDS = 5.0
PDF_BUDGET_RSS_INCREASE = 200 * 2**20  # octets

RENDER_SCRIPT = """
import json, resource, sys
import django
django.setup()
from datetime import date
from apps.people.models import Employee
from apps.planning import exports, services

def peak():
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return value if sys.platform == "darwin" else value * 1024

first, last = date(2026, 10, 1), date(2026, 10, 31)
kinds = [services.SITE, services.TELEWORK, services.LEAVE, services.SITE, services.SITE]
rows = []
for n in range(services.MAX_PDF_PEOPLE):
    cells = [
        services.Cell(day, services.WEEKEND if day.weekday() >= 5 else kinds[(n + day.day) % 5],
                      on_call=day.day % 7 == 0, leave_label="Autre absence")
        for day in services.days(first, last)
    ]
    rows.append(services.Row(Employee(first_name=f"Prénom{n}", last_name=f"Nom{n:03d}"), cells))

class Company:
    name, slug, logo = "Exemple SAS", "exemple", None

before = peak()
pdf = exports._pdf(rows, first, last, Company())
after = peak()
print(json.dumps({"before": before, "after": after, "size": len(pdf)}))
"""


def test_largest_allowed_pdf_time(client_for, company_a):
    client = client_for(company_a.hr)
    populate(company_a, 60)
    url = MONTH_EXPORT + "pdf&page=1"
    client.get(url)  # chargement des polices et des gabarits
    elapsed, response = median_seconds(lambda: client.get(url))  # médiane de 3 exécutions
    assert response.status_code == 200 and response.content.startswith(b"%PDF")
    print(f"\nPDF 50 personnes x 31 jours (médiane de 3) : {elapsed * 1000:.0f} ms")
    assert elapsed < PDF_BUDGET_SECONDS, f"{elapsed * 1000:.0f} ms"


def test_largest_allowed_pdf_resident_memory():
    env = {
        **os.environ,
        "DJANGO_SETTINGS_MODULE": "config.settings.test",
        "PDF_SCRIPT": RENDER_SCRIPT,
        "PYTHON": sys.executable,
    }
    # Deux commandes : le shell ne remplace pas son processus par Python (pas d'« exec »).
    command = '"$PYTHON" -c "import os; exec(os.environ[\'PDF_SCRIPT\'])"; exit $?'
    result = subprocess.run(  # noqa: S603 (commande fixe, aucun paramètre extérieur)
        ["/bin/sh", "-c", command],
        cwd=Path(settings.BASE_DIR),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
    )
    measure = json.loads(result.stdout.strip().splitlines()[-1])
    increase = measure["after"] - measure["before"]
    print(
        f"\nPDF 50 personnes x 31 jours : mémoire résidente {measure['before'] / 2**20:.0f} Mio "
        f"avant le rendu, {measure['after'] / 2**20:.0f} Mio au maximum "
        f"(hausse {increase / 2**20:.0f} Mio), fichier de {measure['size'] // 1024} Kio"
    )
    assert measure["size"] > 0
    assert increase < PDF_BUDGET_RSS_INCREASE, f"{increase / 2**20:.0f} Mio"
