"""Planning : critères d'acceptation de docs/modules/06-planning.md."""

from datetime import date, timedelta
from html import unescape

import pytest
from django.utils import timezone

from apps.agenda.days import holidays_between
from apps.approvals import workflow
from apps.approvals.models import OnCallDeclaration
from apps.approvals.tests.conftest import next_weekday
from apps.core.models import CompanyModule, Module, Service
from apps.core.tenancy import tenant_context
from apps.people.models import Employee
from apps.planning import services
from tests.factories import EmployeeFactory, ServiceFactory

pytestmark = pytest.mark.django_db


def page(client, **params):
    query = "&".join(f"{k}={v}" for k, v in params.items())
    response = client.get(f"/planning/?{query}")
    assert response.status_code == 200
    return unescape(response.content.decode())


def week_param(day):
    return day.isoformat()


@pytest.fixture
def other_service(company_a):
    with tenant_context(company_a.company):
        finance = ServiceFactory(company=company_a.company, name="Finance")
        outsider = EmployeeFactory(
            company=company_a.company, service=finance, first_name="Oscar", last_name="Ailleurs"
        )
    return finance, outsider


# ---------- Périmètre ----------


def test_employee_sees_only_their_service_even_with_a_forged_filter(
    client_for, company_a, other_service
):
    finance, outsider = other_service
    client = client_for(company_a.employee)
    content = page(client)
    assert company_a.manager.full_name in content and outsider.full_name not in content
    forged = page(client, service=finance.pk)
    assert outsider.full_name not in forged
    assert "Tous les services" not in forged  # pas de filtre de service hors RH
    assert outsider.full_name not in page(client, q="Oscar")


def test_manager_also_sees_team_members_of_other_services(client_for, company_a, other_service):
    _finance, outsider = other_service
    Employee.all_companies.filter(pk=outsider.pk).update(manager=company_a.manager)
    assert outsider.full_name in page(client_for(company_a.manager))


def test_hr_sees_the_whole_company_and_filters_by_service(client_for, company_a, other_service):
    finance, outsider = other_service
    client = client_for(company_a.hr)
    content = page(client)
    assert outsider.full_name in content and company_a.employee.full_name in content
    filtered = page(client, service=finance.pk)
    assert outsider.full_name in filtered and company_a.employee.full_name not in filtered


def test_user_comes_first_with_you(client_for, company_a):
    content = page(client_for(company_a.employee))
    first_row = content.index("<tbody>")
    assert content.index(company_a.employee.full_name, first_row) < content.index(
        company_a.manager.full_name, first_row
    )
    assert "(vous)" in content


def test_left_people_are_not_shown(client_for, company_a):
    Employee.all_companies.filter(pk=company_a.manager.pk).update(status="left")
    assert company_a.manager.full_name not in page(client_for(company_a.employee))


# ---------- Cases ----------


def test_telework_validated_is_full_pending_is_hatched_refused_is_absent(
    client_for, company_a, submit
):
    monday = next_weekday()
    validated = submit(company_a, company_a.employee, date=monday + timedelta(days=1)).request
    refused = submit(company_a, company_a.manager, date=monday + timedelta(days=2)).request
    with tenant_context(company_a.company):
        workflow.approve(validated, company_a.manager)
        workflow.refuse(refused, company_a.hr, reason="Non")
        rows = services.build_rows(
            [company_a.employee, company_a.manager], monday, monday + timedelta(days=6)
        )
    camille, louise = (row.cells for row in rows)
    assert (camille[0].state, camille[0].pending) == ("tt", True)  # fixture : lundi en attente
    assert (camille[1].state, camille[1].pending) == ("tt", False)
    assert louise[2].state == "site"  # refusé : n'apparaît pas
    content = page(client_for(company_a.employee), date=week_param(monday))
    assert "Télétravail (en attente)" in content and "k-tt pend" in content


def test_christmas_is_empty_and_marked_as_holiday(client_for, company_a):
    year = timezone.localdate().year
    christmas = date(year, 12, 25)
    while christmas.weekday() >= 5:
        christmas = date(christmas.year + 1, 12, 25)
    content = page(client_for(company_a.employee), date=christmas.isoformat())
    assert "Noël (férié)" in content
    with tenant_context(company_a.company):
        cell = services.build_rows([company_a.employee], christmas, christmas)[0].cells[0]
    assert cell.state == "off" and not cell.clickable


def test_on_call_adds_an_a_marker_even_on_a_weekend(client_for, company_a, submit):
    monday = next_weekday(offset_days=21)
    submit(
        company_a,
        company_a.manager,
        OnCallDeclaration,
        start=monday + timedelta(days=4),
        end=monday + timedelta(days=6),
    )
    with tenant_context(company_a.company):
        cells = services.build_rows([company_a.manager], monday, monday + timedelta(days=6))[
            0
        ].cells
    assert [c.on_call for c in cells] == [False] * 4 + [True] * 3
    assert cells[5].state == "we" and cells[5].label == "Week-end, astreinte en attente"
    content = page(client_for(company_a.manager), date=monday.isoformat())
    assert 'class="cell-oncall pend"' in content


def test_dash_before_arrival(client_for, company_a):
    arrival = next_weekday(offset_days=7, weekday=3)
    Employee.all_companies.filter(pk=company_a.manager.pk).update(
        arrival_date=arrival, status="upcoming"
    )
    with tenant_context(company_a.company):
        manager = Employee.objects.get(pk=company_a.manager.pk)
        cells = services.build_rows([manager], arrival - timedelta(days=3), arrival)[0].cells
    assert [c.state for c in cells] == ["none", "none", "none", "site"]
    assert "Pas encore arrivé" in page(client_for(company_a.employee), date=arrival.isoformat())


def test_own_future_site_day_opens_the_prefilled_telework_modal(client_for, company_a):
    monday = next_weekday()
    content = page(client_for(company_a.employee), date=monday.isoformat())
    tuesday = (monday + timedelta(days=1)).isoformat()
    assert f'hx-get="/teletravail/nouvelle/?date={tuesday}"' in content
    assert "Déclarer du télétravail" in content
    # Pas sur les journées des autres, ni sur un jour déjà en télétravail (lundi).
    assert f'/teletravail/nouvelle/?date={monday.isoformat()}"' not in content
    modal = client_for(company_a.employee).get(f"/teletravail/nouvelle/?date={tuesday}")
    assert f'value="{tuesday}"' in modal.content.decode()


def test_month_view_shows_letters_and_the_month_title(client_for, company_a):
    content = page(client_for(company_a.employee), vue="mois", date="2026-10-01")
    assert "octobre 2026" in content
    assert 'class="cell m k-site" aria-hidden="true">S' in content


def test_week_title_and_navigation(client_for, company_a):
    content = page(client_for(company_a.employee), date="2026-10-21")
    assert "Semaine du 19 oct. au 25 octobre 2026" in content
    assert "date=2026-10-12" in content and "date=2026-10-26" in content


def test_pagination_keeps_you_on_every_page(client_for, company_a):
    with tenant_context(company_a.company):
        for n in range(55):
            EmployeeFactory(
                company=company_a.company,
                service=company_a.service,
                site=company_a.site,
                last_name=f"Zz{n:02d}",
                user=None,
            )
    client = client_for(company_a.employee)
    first = page(client)
    second = page(client, page=2)
    assert "(vous)" in first and "(vous)" in second
    assert "1 à 50 sur" in first
    assert first.count('<th class="nm" scope="row">') == 51


def test_footer_counts_people_and_present_today(client_for, company_a):
    content = page(client_for(company_a.employee))
    assert "5 personnes ·" in content and "sur site aujourd'hui" in content


def test_disabled_planning_module(client_for, company_a):
    CompanyModule.all_companies.filter(company=company_a.company, module=Module.PLANNING).update(
        enabled=False
    )
    response = client_for(company_a.employee).get("/planning/")
    assert response.status_code == 403 and "Module désactivé" in response.content.decode()
    assert (
        "Voir le planning"
        not in client_for(company_a.employee).get("/teletravail/").content.decode()
    )


def test_view_planning_links_are_shown(client_for, company_a):
    for path in ("/teletravail/", "/conges/", "/astreintes/"):
        content = client_for(company_a.employee).get(path).content.decode()
        assert 'href="/planning/"' in content and "Voir le planning" in content
    assert (
        "Voir les absences du service au planning"
        in client_for(company_a.employee).get("/conges/").content.decode()
    )


def test_planning_lists_only_the_current_company(client_for, company_a, company_b):
    assert company_b.employee.full_name not in page(client_for(company_a.hr))


def test_no_holiday_free_week_assumption_is_needed():
    # Garde-fou des tests : la semaine de next_weekday() n'a pas de jour férié.
    monday = next_weekday()
    assert not holidays_between(monday, monday + timedelta(days=4))


def test_service_filter_of_another_company_shows_nobody(client_for, company_a, company_b):
    with tenant_context(company_b.company):
        foreign = Service.objects.first()
    content = page(client_for(company_a.hr), service=foreign.pk)
    assert "Aucun collaborateur ne correspond aux filtres." in content
