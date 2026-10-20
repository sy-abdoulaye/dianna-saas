"""Fermetures (T-16, L4-03, L4-04) : administrateur seul, RH en lecture ; le télétravail est
refusé les jours fériés et fermés ; les RH sont prévenus avec la liste des demandes."""

import json
from datetime import date, timedelta

import pytest
from django.utils import timezone

from apps.agenda.days import holidays_between
from apps.agenda.models import Closure
from apps.approvals import workflow
from apps.approvals.models import LeaveRequest, OnCallDeclaration, TeleworkRequest
from apps.approvals.tests.conftest import next_weekday
from apps.core.models import AuditLog, Notification, Site
from apps.core.tenancy import tenant_context
from tests.factories import EmployeeFactory

pytestmark = pytest.mark.django_db
URL = "/administration/fermetures/"


def toast(response):
    return json.loads(response["HX-Trigger"])["toast"]


def future_weekday(days=21):
    """Jour ouvré à venir, hors jour férié."""
    day = timezone.localdate() + timedelta(days=days)
    while day.weekday() >= 5 or holidays_between(day, day):
        day += timedelta(days=1)
    return day


def weekday_holiday(alsace=False):
    """Prochain jour férié tombant un jour de semaine (et absent du calendrier national si
    `alsace`)."""
    today = timezone.localdate()
    for year in range(today.year, today.year + 8):
        found = holidays_between(date(year, 1, 1), date(year, 12, 31), alsace=alsace)
        national = holidays_between(date(year, 1, 1), date(year, 12, 31))
        for day, label in sorted(found.items()):
            if day > today and day.weekday() < 5 and (not alsace or day not in national):
                return day, label
    raise AssertionError("aucun jour férié trouvé")


@pytest.mark.parametrize(("who", "status"), [("employee", 403), ("manager", 403), ("hr", 200)])
def test_only_admin_and_hr_see_closures(client_for, company_a, who, status):
    assert client_for(getattr(company_a, who)).get(URL).status_code == status


def test_hr_reads_but_cannot_change_closures(client_for, company_a):
    client = client_for(company_a.hr)
    page = client.get(URL).content.decode()
    assert "Ajouter une fermeture" not in page
    assert "Utilisateurs et profils" not in page  # seul l'onglet Fermetures pour les RH
    assert client.get(f"{URL}ajouter/").status_code == 403
    closure = company_a.requests["closure"]
    assert client.post(f"{URL}{closure.pk}/supprimer/").status_code == 403


def test_admin_adds_a_closure_and_hr_get_the_list_of_requests(client_for, company_a):
    day = future_weekday()
    with tenant_context(company_a.company):
        colleague = EmployeeFactory(
            company=company_a.company, site=company_a.site, first_name="Nina", last_name="Petit"
        )
        for person in (company_a.employee, colleague):
            TeleworkRequest.objects.create(requester=person, date=day, submitted_at=timezone.now())
        other_site = EmployeeFactory(company=company_a.company, first_name="Paul")
        TeleworkRequest.objects.create(requester=other_site, date=day, submitted_at=timezone.now())
    response = client_for(company_a.admin).post(
        f"{URL}ajouter/", {"date": day.isoformat(), "label": "Pont", "site": company_a.site.pk}
    )
    assert response.status_code == 204
    assert "2 demande(s) de télétravail concernée(s)" in toast(response)["message"]
    with tenant_context(company_a.company):
        note = Notification.objects.get(recipient=company_a.hr, text__startswith="Fermeture")
        assert company_a.employee.full_name in note.text and "Nina Petit" in note.text
        assert "Paul" not in note.text  # autre site
        assert note.url.startswith(URL)
        # Les demandes restent en place (L4-03).
        assert TeleworkRequest.objects.filter(date=day, status="pending").count() == 3
        log = AuditLog.objects.get(action="company.closure_added")
        assert "Nina" not in log.summary and "Pont" in log.summary
    page = client_for(company_a.hr).get(URL).content.decode()
    assert "Nina Petit" in page and "2 demandes de télétravail concernées" in page


def test_closure_form_errors(client_for, company_a):
    client = client_for(company_a.admin)
    past = client.post(f"{URL}ajouter/", {"date": "2020-01-06", "label": "Ancien", "site": ""})
    assert past.status_code == 422 and "La date est passée." in past.content.decode()
    closure = company_a.requests["closure"]
    twice = client.post(
        f"{URL}ajouter/", {"date": closure.date.isoformat(), "label": "Doublon", "site": ""}
    )
    assert "Une fermeture existe déjà ce jour-là pour ce périmètre." in twice.content.decode()


def test_admin_deletes_a_closure(client_for, company_a):
    closure = company_a.requests["closure"]
    response = client_for(company_a.admin).post(f"{URL}{closure.pk}/supprimer/")
    assert response.status_code == 204
    assert not Closure.all_companies.filter(pk=closure.pk).exists()
    assert AuditLog.all_companies.filter(action="company.closure_deleted").exists()


def test_site_holidays_setting(client_for, company_a):
    response = client_for(company_a.admin).post(
        f"/administration/structure/sites/{company_a.site.pk}/renommer/",
        {"name": "Lyon", "alsace_moselle": "on"},
    )
    assert response.status_code == 204
    assert Site.all_companies.get(pk=company_a.site.pk).alsace_moselle
    assert AuditLog.all_companies.filter(action="company.site_holidays_changed").exists()
    service_form = client_for(company_a.admin).get(
        f"/administration/structure/services/{company_a.service.pk}/renommer/"
    )
    assert "Alsace-Moselle" not in service_form.content.decode()


# ---------- Télétravail refusé les jours non ouvrés ----------


def test_telework_is_refused_on_a_holiday(client_for, company_a):
    day, label = weekday_holiday()
    response = client_for(company_a.employee).post(
        "/teletravail/nouvelle/", {"date": day.isoformat()}
    )
    assert response.status_code == 422
    assert f"est un jour férié ({label})." in response.content.decode()


def test_telework_is_refused_on_a_closure_but_leave_and_on_call_are_not(company_a, submit):
    day = future_weekday()
    with tenant_context(company_a.company):
        Closure.objects.create(date=day, label="Inventaire")
    with pytest.raises(workflow.RequestValidationError) as error:
        submit(company_a, company_a.employee, date=day)
    assert "L'entreprise est fermée le" in str(error.value.message)
    submit(company_a, company_a.manager, LeaveRequest, start=day, end=day, leave_type="other")
    submit(company_a, company_a.manager, OnCallDeclaration, start=day, end=day)


def test_alsace_moselle_holiday_only_for_that_site(company_a, submit):
    st_stephen, _label = weekday_holiday(alsace=True)
    with tenant_context(company_a.company):
        Site.objects.filter(pk=company_a.site.pk).update(alsace_moselle=True)
    with pytest.raises(workflow.RequestValidationError):
        submit(company_a, company_a.employee, date=st_stephen)
    with tenant_context(company_a.company):
        Site.objects.filter(pk=company_a.site.pk).update(alsace_moselle=False)
    submit(company_a, company_a.employee, date=st_stephen)


def test_undo_of_a_cancellation_is_refused_on_a_new_closure(company_a, submit):
    day = next_weekday(offset_days=14, weekday=3)
    result = submit(company_a, company_a.employee, date=day)
    with tenant_context(company_a.company):
        cancelled = workflow.cancel(result.request, company_a.employee)
        Closure.objects.create(date=day, label="Inventaire")
        with pytest.raises(workflow.WorkflowError) as error:
            workflow.undo(TeleworkRequest, cancelled.undo_payload("cancel"), company_a.employee)
    assert "fermée" in str(error.value.message)
