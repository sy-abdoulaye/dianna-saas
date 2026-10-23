"""Écrans des demandes : critères d'acceptation de docs/modules/05-demandes.md."""

import json
from datetime import timedelta
from decimal import Decimal

import pytest
from django.core import mail
from django.utils import timezone

from apps.agenda.models import CalendarEvent
from apps.approvals.models import (
    LeaveRequest,
    OnCallDeclaration,
    RequestStatus,
    SummerCampaign,
    TeleworkRequest,
)
from apps.approvals.tests.conftest import next_weekday
from apps.core.models import CompanyModule, Module, Notification
from apps.core.tenancy import tenant_context
from apps.people.models import Employee

pytestmark = pytest.mark.django_db


def trigger(response):
    return json.loads(response["HX-Trigger"])


def send_telework(client, day):
    return client.post("/teletravail/nouvelle/", {"date": day.isoformat()})


# ---------- Télétravail ----------


def test_third_day_in_a_week_is_refused_with_week_and_maximum(client_for, company_a):
    client = client_for(company_a.employee)
    # La fixture a déjà le lundi de la semaine prochaine (en attente).
    assert send_telework(client, next_weekday(weekday=1)).status_code == 204
    response = send_telework(client, next_weekday(weekday=3))
    assert response.status_code == 422
    content = response.content.decode()
    monday = next_weekday()
    assert "Vous avez déjà 2 jours de télétravail la semaine du" in content
    assert monday.strftime("%-d") in content and "(maximum 2)" in content


@pytest.mark.parametrize(
    ("day", "message"),
    [
        (
            timezone.localdate() - timedelta(days=1),
            "Ce jour est passé. Choisissez une date à partir d",
        ),
        (next_weekday(weekday=5), "Le télétravail se déclare du lundi au vendredi."),
        (next_weekday(), "Vous avez déjà une demande pour ce jour."),
    ],
)
def test_telework_controls(client_for, company_a, day, message):
    content = send_telework(client_for(company_a.employee), day).content.decode()
    assert message in content.replace("&#x27;", "'")


def test_individual_override_replaces_the_company_quota(client_for, company_a):
    Employee.all_companies.filter(pk=company_a.employee.pk).update(telework_days_override=1)
    response = send_telework(client_for(company_a.employee), next_weekday(weekday=2))
    assert "(maximum 1)" in response.content.decode()


def test_sending_creates_the_pending_event_and_offers_undo(client_for, company_a, run_tasks):
    client = client_for(company_a.employee)
    response = send_telework(client, next_weekday(weekday=4))
    toast = trigger(response)["toast"]
    assert toast["title"] == "Demande envoyée"
    assert company_a.manager.full_name in toast["message"]
    with tenant_context(company_a.company):
        request = TeleworkRequest.objects.get(date=next_weekday(weekday=4))
        assert (
            CalendarEvent.objects.get(source_id=request.pk, source_type="telework").status
            == "pending"
        )
    undo = client.post(toast["undo_url"])
    assert trigger(undo)["toast"]["title"] == "Envoi annulé"
    assert not TeleworkRequest.all_companies.filter(pk=request.pk).exists()
    run_tasks(after_seconds=46)
    assert mail.outbox == []  # l'e-mail « à valider » n'est jamais parti


def test_auto_approval_option_is_announced(client_for, company_a):
    from apps.core.models import Company

    Company.objects.filter(pk=company_a.company.pk).update(telework_auto_approve=True)
    response = send_telework(client_for(company_a.employee), next_weekday(weekday=4))
    assert trigger(response)["toast"]["title"] == "Demande validée"


# ---------- Validation ----------


def test_manager_sees_only_the_team_and_cannot_validate_own(client_for, company_a, submit):
    own = submit(company_a, company_a.manager).request
    client = client_for(company_a.manager)
    content = client.get("/teletravail/?onglet=a-valider").content.decode()
    assert company_a.employee.full_name in content
    assert "Mon équipe" in content
    response = client.post(f"/teletravail/{own.public_id}/valider/")
    assert response.status_code == 409


def test_hr_to_validate_only_shows_people_without_manager(client_for, company_a, submit):
    submit(company_a, company_a.manager)  # Louise : sans manager
    content = client_for(company_a.hr).get("/teletravail/?onglet=a-valider").content.decode()
    assert company_a.manager.full_name in content
    assert company_a.employee.full_name not in content
    assert "Toutes les demandes" in content


def test_two_quick_clicks_make_one_transition(client_for, company_a):
    request = company_a.requests["telework"]
    client = client_for(company_a.manager)
    assert client.post(f"/teletravail/{request.public_id}/valider/").status_code == 204
    second = client.post(f"/teletravail/{request.public_id}/valider/")
    assert second.status_code == 409
    assert trigger(second)["toast"]["title"] == "Cette demande a déjà été traitée."


def test_refusal_needs_a_reason_visible_in_the_history(client_for, company_a):
    request = company_a.requests["telework"]
    client = client_for(company_a.manager)
    url = f"/teletravail/{request.public_id}/refuser/"
    empty = client.post(url, {"reason": ""})
    assert empty.status_code == 422 and "Indiquez le motif du refus." in empty.content.decode()
    assert client.post(url, {"reason": "Réunion d'équipe"}).status_code == 204
    detail = client_for(company_a.employee).get(f"/teletravail/{request.public_id}/")
    assert "Réunion d" in detail.content.decode() and "Demande refusée" in detail.content.decode()
    assert not CalendarEvent.all_companies.filter(
        source_id=request.pk, source_type="telework"
    ).exists()


def test_undo_after_validation_restores_pending_and_removes_the_notification(client_for, company_a):
    request = company_a.requests["telework"]
    client = client_for(company_a.manager)
    response = client.post(f"/teletravail/{request.public_id}/valider/")
    note_count = Notification.all_companies.filter(recipient=company_a.employee).count()
    undo = client.post(trigger(response)["toast"]["undo_url"])
    assert trigger(undo)["toast"]["title"] == "Décision annulée"
    request.refresh_from_db()
    assert request.status == RequestStatus.PENDING
    assert Notification.all_companies.filter(recipient=company_a.employee).count() == note_count - 1


def test_undo_token_of_another_company_is_refused(client_for, company_a, company_b):
    response = client_for(company_a.manager).post(
        f"/teletravail/{company_a.requests['telework'].public_id}/valider/"
    )
    undo_url = trigger(response)["toast"]["undo_url"]
    assert client_for(company_b.manager).post(undo_url).status_code == 409


def test_hr_acting_for_the_manager_sees_the_warning(client_for, company_a):
    request = company_a.requests["telework"]
    content = client_for(company_a.hr).get(f"/teletravail/{request.public_id}/").content.decode()
    assert f"Vous agissez à la place de {company_a.manager.full_name}." in content


def test_colleague_cannot_see_someone_else_request(client_for, company_a):
    other = Employee.all_companies.get(pk=company_a.pending.pk)
    del other
    from tests.factories import EmployeeFactory

    colleague = EmployeeFactory(company=company_a.company)
    response = client_for(colleague).get(
        f"/teletravail/{company_a.requests['telework'].public_id}/"
    )
    assert response.status_code == 404


# ---------- Annulations ----------


def test_requester_cancels_pending_only(client_for, company_a):
    request = company_a.requests["telework"]
    client = client_for(company_a.employee)
    assert (
        "Annuler cette demande"
        in client.get(f"/teletravail/{request.public_id}/annuler/").content.decode()
    )
    assert client.post(f"/teletravail/{request.public_id}/annuler/").status_code == 204
    request.refresh_from_db()
    assert request.status == RequestStatus.CANCELLED


def test_hr_cancels_an_approved_request_with_a_reason(client_for, company_a, run_tasks):
    request = company_a.requests["telework"]
    client_for(company_a.manager).post(f"/teletravail/{request.public_id}/valider/")
    assert (
        client_for(company_a.employee)
        .get(f"/teletravail/{request.public_id}/annuler-validee/")
        .status_code
        == 404
    )
    client = client_for(company_a.hr)
    url = f"/teletravail/{request.public_id}/annuler-validee/"
    assert "Annuler une demande validée" in client.get(url).content.decode()
    assert client.post(url, {"reason": ""}).status_code == 422
    assert client.post(url, {"reason": "Fermeture du site"}).status_code == 204
    request.refresh_from_db()
    assert request.status == RequestStatus.CANCELLED
    run_tasks(after_seconds=46)
    assert any(
        m.to == [company_a.employee.user.email] and "annulée" in m.subject for m in mail.outbox
    )


# ---------- Congés et campagnes ----------


def leave_data(campaign, **overrides):
    start = campaign.period_start + timedelta(days=40)
    data = {
        "start": start.isoformat(),
        "end": (start + timedelta(days=4)).isoformat(),
        "leave_type": "summer",
    }
    data.update(overrides)
    return data


def test_leave_controls(client_for, company_a):
    campaign = company_a.requests["campaign"]
    client = client_for(company_a.manager)
    start = campaign.period_start + timedelta(days=40)
    too_long = client.post(
        "/conges/nouvelle/", leave_data(campaign, end=(start + timedelta(days=31)).isoformat())
    ).content.decode()
    assert "Une demande couvre au maximum 31 jours. Faites deux demandes." in too_long
    outside = client.post(
        "/conges/nouvelle/", leave_data(campaign, start="2027-10-04", end="2027-10-08")
    ).content.decode()
    assert "sont compris entre le" in outside
    reversed_dates = client.post(
        "/conges/nouvelle/", leave_data(campaign, end=(start - timedelta(days=1)).isoformat())
    ).content.decode()
    assert "Le dernier jour doit être après le premier." in reversed_dates
    assert client.post("/conges/nouvelle/", leave_data(campaign)).status_code == 204
    overlap = client.post("/conges/nouvelle/", leave_data(campaign)).content.decode()
    assert "Cette période chevauche une de vos demandes existantes." in overlap


def test_conflict_is_shown_to_the_validator(client_for, company_a, submit):
    leave = company_a.requests["leave"]  # Camille, Support client
    from tests.factories import EmployeeFactory

    colleague = EmployeeFactory(
        company=company_a.company,
        service=company_a.service,
        manager=company_a.manager,
        first_name="Nina",
    )
    submit(company_a, colleague, LeaveRequest, start=leave.start, end=leave.end)
    content = client_for(company_a.manager).get("/conges/?onglet=a-valider").content.decode()
    assert "absence dans le service sur la période" in content
    detail = client_for(company_a.manager).get(f"/conges/{leave.public_id}/").content.decode()
    assert "Nina" in detail


def test_summer_requests_without_open_campaign_must_be_other_absence(client_for, company_a):
    SummerCampaign.all_companies.filter(company=company_a.company).update(status="closed")
    response = client_for(company_a.employee).post(
        "/conges/nouvelle/", {"start": "2027-07-05", "end": "2027-07-09", "leave_type": "summer"}
    )
    assert "choisissez « Autre absence »" in response.content.decode()


def test_campaigns_are_managed_by_hr_only(client_for, company_a):
    assert client_for(company_a.employee).get("/conges/campagnes/").status_code == 403
    client = client_for(company_a.hr)
    assert (
        client.post(
            "/conges/campagnes/nouvelle/",
            {
                "label": "Été 2028",
                "period_start": "2028-06-01",
                "period_end": "2028-09-30",
                "deadline": "2028-02-28",
                "conflict_threshold": 30,
            },
        ).status_code
        == 204
    )
    new = SummerCampaign.all_companies.get(label="Été 2028")
    blocked = client.post(f"/conges/campagnes/{new.pk}/ouvrir/")
    assert blocked.status_code == 409  # « Été 2027 » est déjà ouverte
    open_one = company_a.requests["campaign"]
    client.post(f"/conges/campagnes/{open_one.pk}/clore/")
    assert client.post(f"/conges/campagnes/{new.pk}/ouvrir/").status_code == 204
    assert SummerCampaign.all_companies.get(pk=new.pk).status == "open"


# ---------- Astreintes ----------


def test_on_call_controls(client_for, company_a):
    client = client_for(company_a.manager)
    start = next_weekday()
    data = {"kind": "intervention", "start": start.isoformat(), "end": start.isoformat()}
    assert "Indiquez la durée de l" in client.post("/astreintes/nouvelle/", data).content.decode()
    data["hours"] = "25"
    assert "24 heures" in client.post("/astreintes/nouvelle/", data).content.decode()
    data["hours"] = "3.5"
    assert client.post("/astreintes/nouvelle/", data).status_code == 204
    on_call = {
        "kind": "on_call",
        "start": start.isoformat(),
        "end": (start + timedelta(days=6)).isoformat(),
    }
    assert client.post("/astreintes/nouvelle/", on_call).status_code == 204
    overlap = client.post("/astreintes/nouvelle/", on_call).content.decode()
    assert "Cette astreinte chevauche une de vos astreintes déclarées." in overlap
    assert OnCallDeclaration.all_companies.filter(requester=company_a.manager).count() == 2


# ---------- Module désactivé, menu, fiche ----------


@pytest.mark.parametrize(
    "url", ["/teletravail/", "/teletravail/nouvelle/", "/conges/", "/astreintes/"]
)
def test_disabled_module_shows_the_dedicated_page(client_for, company_a, url):
    module = {"te": Module.TELEWORK, "co": Module.SUMMER_LEAVE, "as": Module.ON_CALL}[url[1:3]]
    with tenant_context(company_a.company):
        CompanyModule.objects.filter(module=module).update(enabled=False)
    client = client_for(company_a.employee)
    response = client.get(url)
    assert response.status_code == 403
    assert "Module désactivé" in response.content.decode()
    menu = client.get("/").content.decode()
    assert f'href="{url}"' not in menu
    # Les données sont conservées.
    assert TeleworkRequest.all_companies.filter(company=company_a.company).exists()


def test_menu_counter_matches_the_to_validate_tab(client_for, company_a):
    content = client_for(company_a.manager).get("/").content.decode()
    assert "1 à traiter" in content  # la demande de télétravail de Camille


def test_record_shows_requests_tab_to_self_manager_and_hr(client_for, company_a):
    url = f"/annuaire/{company_a.employee.public_id}/?onglet=demandes"
    for viewer in (company_a.employee, company_a.manager, company_a.hr):
        content = client_for(viewer).get(url).content.decode()
        assert "Télétravail" in content and "En attente" in content
    from tests.factories import EmployeeFactory

    colleague = EmployeeFactory(company=company_a.company)
    assert "En attente" not in client_for(colleague).get(url).content.decode()


def test_on_call_hours_accept_a_comma(client_for, company_a):
    """Champ texte décimal (L5-20) : « 2,5 » et « 2.5 » acceptés, tout autre format refusé."""
    client = client_for(company_a.manager)
    start = next_weekday(14)
    data = {"kind": "intervention", "start": start.isoformat(), "end": start.isoformat()}
    page = client.get("/astreintes/nouvelle/").content.decode()
    assert 'inputmode="decimal"' in page and 'type="number"' not in page
    for wrong in ("2;5", "deux", "2,5,1", "-2"):
        data["hours"] = wrong
        assert (
            "Saisissez une durée comme 2,5."
            in client.post("/astreintes/nouvelle/", data).content.decode()
        )
    data["hours"] = "2,5"
    assert client.post("/astreintes/nouvelle/", data).status_code == 204
    saved = OnCallDeclaration.all_companies.filter(requester=company_a.manager).latest("pk")
    assert saved.hours == Decimal("2.5")
