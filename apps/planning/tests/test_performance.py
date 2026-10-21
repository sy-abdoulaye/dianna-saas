"""Performance du planning (docs/modules/06-planning.md) : 200 personnes × 31 jours en moins de
300 ms côté serveur, pour la vue mois et pour l'export d'un mois ; nombre de requêtes
indépendant de l'effectif (jamais de requête par case)."""

import time
from datetime import date, timedelta

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.agenda.models import CalendarEvent, Closure
from apps.core.tenancy import tenant_context
from apps.people.models import Employee

# Mesuré sans couverture (second passage de `make test`) : la couverture ralentit le code.
pytestmark = [pytest.mark.django_db, pytest.mark.perf]
BUDGET_SECONDS = 0.3
MONTH = date(2026, 10, 1)


def populate(company_data, count, start=0):
    """`count` personnes du même service, chacune avec du télétravail, un congé et une
    astreinte dans le mois. Création directe en base : entreprise, service et site sont
    vérifiés identiques (CLAUDE.md, règle 1)."""
    company = company_data.company
    assert company_data.service.company_id == company.pk == company_data.site.company_id
    with tenant_context(company):
        people = Employee.objects.bulk_create(
            [
                Employee(
                    company=company,
                    first_name=f"Prénom{n}",
                    last_name=f"Nom{n:03d}",
                    email=f"perf{n}@exemple.fr",
                    service=company_data.service,
                    site=company_data.site,
                )
                for n in range(start, start + count)
            ]
        )
        events = []
        for n, person in enumerate(people, start=start):
            for offset in (1, 8, 15, 22):
                day = MONTH + timedelta(days=offset + n % 3)
                events.append(
                    CalendarEvent(
                        company=company,
                        employee=person,
                        kind="telework",
                        start=day,
                        end=day,
                        status="approved",
                        source_type="telework",
                        source_id=10_000 + n * 10 + offset,
                    )
                )
            events.append(
                CalendarEvent(
                    company=company,
                    employee=person,
                    kind="leave",
                    start=MONTH + timedelta(days=11),
                    end=MONTH + timedelta(days=13),
                    source_type="leave",
                    source_id=90_000 + n,
                )
            )
            events.append(
                CalendarEvent(
                    company=company,
                    employee=person,
                    kind="on_call",
                    start=MONTH + timedelta(days=16),
                    end=MONTH + timedelta(days=18),
                    source_type="on_call",
                    source_id=95_000 + n,
                )
            )
        CalendarEvent.objects.bulk_create(events)
        Closure.objects.get_or_create(
            date=MONTH + timedelta(days=29), site=None, defaults={"label": "Inventaire"}
        )


def timed(client, url):
    client.get(url)  # premier appel : chargement des gabarits et des caches
    with CaptureQueriesContext(connection) as queries:
        start = time.perf_counter()
        response = client.get(url)
        elapsed = time.perf_counter() - start
    assert response.status_code == 200
    return elapsed, len(queries), response


MONTH_VIEW = f"/planning/?vue=mois&date={MONTH.isoformat()}"
MONTH_EXPORT = (
    "/planning/export/fichier/?periode=personnalisee&debut=2026-10-01&fin=2026-10-31&format="
)


@pytest.mark.parametrize("url", [MONTH_VIEW, MONTH_EXPORT + "csv", MONTH_EXPORT + "xlsx"])
def test_month_for_200_people_under_300_ms_with_constant_queries(client_for, company_a, url):
    client = client_for(company_a.hr)
    populate(company_a, 20)
    _small, small_queries, _r = timed(client, url)
    populate(company_a, 180, start=20)
    elapsed, queries, response = timed(client, url)
    assert Employee.all_companies.filter(company=company_a.company).count() >= 200
    assert queries == small_queries, "une requête par personne ou par case"
    assert elapsed < BUDGET_SECONDS, f"{elapsed * 1000:.0f} ms"
    if "format=csv" in url:
        assert response.content.decode("utf-8-sig").count("\n") >= 200


def test_month_grid_of_200_people_on_a_single_page(company_a, monkeypatch):
    """Même sans pagination, le calcul de la grille reste sous le budget."""
    from apps.planning import services

    populate(company_a, 200)
    monkeypatch.setattr(services, "PER_PAGE", 500)
    with tenant_context(company_a.company):
        hr = Employee.objects.get(pk=company_a.hr.pk)
        start = time.perf_counter()
        grid = services.grid(hr, view="mois", anchor=MONTH, today=timezone.localdate())
        elapsed = time.perf_counter() - start
    assert len(grid.rows) >= 200 and len(grid.days) == 31
    assert elapsed < BUDGET_SECONDS, f"{elapsed * 1000:.0f} ms"


PDF_BUDGET_SECONDS = 5.0
PDF_BUDGET_MEMORY = 200 * 1024 * 1024  # octets (allocations Python, tracemalloc)


def test_largest_allowed_pdf_50_people_over_a_month(client_for, company_a):
    """Le plus gros PDF autorisé (L4-17) : une page du planning (50 personnes), un mois.
    Temps mesuré seul, puis mémoire (tracemalloc ralentit le code)."""
    import tracemalloc

    client = client_for(company_a.hr)
    populate(company_a, 60)
    url = MONTH_EXPORT + "pdf&page=1"
    client.get(url)  # chargement des polices et des gabarits
    start = time.perf_counter()
    response = client.get(url)
    elapsed = time.perf_counter() - start
    assert response.status_code == 200 and response.content.startswith(b"%PDF")
    tracemalloc.start()
    client.get(url)
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    print(f"\nPDF 50 personnes x 31 jours : {elapsed * 1000:.0f} ms, pic {peak / 2**20:.0f} Mio")
    assert elapsed < PDF_BUDGET_SECONDS, f"{elapsed * 1000:.0f} ms"
    assert peak < PDF_BUDGET_MEMORY, f"{peak / 2**20:.0f} Mio"
