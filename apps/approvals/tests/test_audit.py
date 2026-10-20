"""Corrections de l'audit du lot 3 (A3-01 à A3-06), dont les cas de concurrence réels."""

import json
import threading
from datetime import timedelta

import pytest
from django.core import mail
from django.db import connection
from django.test import Client

from apps.approvals import workflow
from apps.approvals.models import (
    LeaveRequest,
    OnCallDeclaration,
    RequestStatus,
    SummerCampaign,
    TeleworkRequest,
)
from apps.approvals.tests.conftest import next_weekday
from apps.core.models import Company, Notification
from apps.core.tenancy import tenant_context
from apps.people.models import Employee
from tests.factories import EmployeeFactory

pytestmark = pytest.mark.django_db

OTHER_DECISION = "Une autre décision a été prise depuis. Rien n'a été modifié."
SAME_DAY = "Vous avez déjà une demande pour ce jour."
OVERLAP = "Cette période chevauche une de vos demandes existantes."


def toast(response):
    return json.loads(response["HX-Trigger"])["toast"]


def run_together(*actions):
    """Lance les actions en même temps, chacune avec sa propre connexion à la base."""
    barrier = threading.Barrier(len(actions))
    outcomes = [None] * len(actions)

    def run(index, action):
        try:
            barrier.wait()
            outcomes[index] = action()
        except Exception as error:
            outcomes[index] = error
        finally:
            connection.close()

    threads = [threading.Thread(target=run, args=item) for item in enumerate(actions)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return outcomes


def messages(outcomes):
    return sorted(
        str(getattr(o, "message", o)) if isinstance(o, Exception) else "ok" for o in outcomes
    )


# ---------- a. Annulation immédiate liée à l'événement de la transition ----------


def test_manager_cannot_undo_after_the_final_hr_decision(client_for, company_a, submit, run_tasks):
    request = submit(company_a, company_a.employee, LeaveRequest).request
    manager = client_for(company_a.manager)
    first = manager.post(f"/conges/{request.public_id}/valider/")
    assert first.status_code == 204
    undo_url = toast(first)["undo_url"]
    assert client_for(company_a.hr).post(f"/conges/{request.public_id}/valider/").status_code == 204

    response = manager.post(undo_url)
    assert response.status_code == 409
    assert toast(response)["title"] == OTHER_DECISION
    request.refresh_from_db()
    assert request.status == RequestStatus.APPROVED and request.decided_by == company_a.hr

    mail.outbox.clear()
    run_tasks(after_seconds=46)
    validated = [m for m in mail.outbox if m.to == [company_a.employee.user.email]]
    assert [m.subject for m in validated] == ["Votre demande de congés a été validée"]


def test_undo_of_the_latest_transition_still_works(company_a, submit):
    request = submit(company_a, company_a.employee).request
    with tenant_context(company_a.company):
        result = workflow.approve(request, company_a.manager)
        assert workflow.undo(TeleworkRequest, result.undo_payload("approve"), company_a.manager)
        stale = result.undo_payload("approve")
        with pytest.raises(workflow.WorkflowError) as error:
            workflow.undo(TeleworkRequest, stale, company_a.manager)  # déjà défaite
    assert str(error.value.message) == OTHER_DECISION


# ---------- b. Contrôles métier dans le service, y compris à l'annulation immédiate ----------


def _cancel_then(client, path, request):
    response = client.post(f"{path}{request.public_id}/annuler/")
    assert response.status_code == 204
    return toast(response)["undo_url"]


def test_undo_of_a_cancellation_respects_the_weekly_quota(client_for, company_a):
    client = client_for(company_a.employee)
    tuesday = client.post("/teletravail/nouvelle/", {"date": next_weekday(weekday=1).isoformat()})
    assert tuesday.status_code == 204
    undo_url = _cancel_then(client, "/teletravail/", company_a.requests["telework"])
    # Le quota (2) est de nouveau atteint par une autre demande de la semaine.
    assert (
        client.post(
            "/teletravail/nouvelle/", {"date": next_weekday(weekday=3).isoformat()}
        ).status_code
        == 204
    )
    response = client.post(undo_url)
    assert response.status_code == 409
    assert "Vous avez déjà 2 jours de télétravail la semaine du" in toast(response)["title"]
    company_a.requests["telework"].refresh_from_db()
    assert company_a.requests["telework"].status == RequestStatus.CANCELLED


def test_undo_of_a_cancellation_respects_the_same_day_rule(client_for, company_a):
    telework = company_a.requests["telework"]
    client = client_for(company_a.employee)
    undo_url = _cancel_then(client, "/teletravail/", telework)
    resent = client.post("/teletravail/nouvelle/", {"date": telework.date.isoformat()})
    assert resent.status_code == 204
    response = client.post(undo_url)  # contrainte de base : jamais d'erreur 500
    assert response.status_code == 409
    assert toast(response)["title"] == SAME_DAY
    telework.refresh_from_db()
    assert telework.status == RequestStatus.CANCELLED


def test_undo_of_a_cancellation_respects_leave_overlaps(client_for, company_a):
    leave = company_a.requests["leave"]
    client = client_for(company_a.employee)
    undo_url = _cancel_then(client, "/conges/", leave)
    response = client.post(
        "/conges/nouvelle/",
        {"start": leave.start.isoformat(), "end": leave.end.isoformat(), "leave_type": "other"},
    )
    assert response.status_code == 204
    response = client.post(undo_url)
    assert response.status_code == 409
    assert toast(response)["title"] == OVERLAP
    leave.refresh_from_db()
    assert leave.status == RequestStatus.CANCELLED


def test_undo_of_an_hr_cancellation_respects_on_call_overlaps(client_for, company_a, submit):
    on_call = company_a.requests["on_call"]
    OnCallDeclaration.all_companies.filter(pk=on_call.pk).update(status=RequestStatus.APPROVED)
    hr = client_for(company_a.hr)
    response = hr.post(f"/astreintes/{on_call.public_id}/annuler-validee/", {"reason": "Erreur"})
    assert response.status_code == 204
    undo_url = toast(response)["undo_url"]
    submit(company_a, company_a.employee, OnCallDeclaration, start=on_call.start, end=on_call.end)
    response = hr.post(undo_url)
    assert response.status_code == 409
    assert toast(response)["title"] == "Cette astreinte chevauche une de vos astreintes déclarées."


def test_submit_checks_live_in_the_service(company_a, submit):
    with pytest.raises(workflow.RequestValidationError) as error:
        submit(company_a, company_a.employee, date=company_a.requests["telework"].date)
    assert error.value.errors == {"date": SAME_DAY}


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    ("first", "second", "expected"),
    [
        # Quota : la fixture a déjà le lundi ; il reste un jour sur deux.
        ({"date": 1}, {"date": 2}, "Vous avez déjà 2 jours"),
        ({"date": 3}, {"date": 3}, SAME_DAY),
    ],
)
def test_simultaneous_telework_submissions(company_a, first, second, expected):
    company = Company.objects.get(pk=company_a.company.pk)
    employee = Employee.all_companies.get(pk=company_a.employee.pk)

    def send(day):
        def action():
            with tenant_context(company):
                return workflow.submit(
                    TeleworkRequest, employee, {"date": next_weekday(weekday=day)}
                )

        return action

    outcomes = run_together(send(first["date"]), send(second["date"]))
    result = messages(outcomes)
    assert result[-1] == "ok" and result[0].startswith(expected)
    assert TeleworkRequest.all_companies.filter(requester=employee, status="pending").count() == 2


@pytest.mark.django_db(transaction=True)
def test_simultaneous_overlapping_leaves(company_a):
    company = Company.objects.get(pk=company_a.company.pk)
    employee = Employee.all_companies.get(pk=company_a.employee.pk)
    start = company_a.requests["campaign"].period_start + timedelta(days=70)

    def send(offset):
        def action():
            with tenant_context(company):
                return workflow.submit(
                    LeaveRequest,
                    employee,
                    {
                        "start": start + timedelta(days=offset),
                        "end": start + timedelta(days=offset + 4),
                        "leave_type": "other",
                    },
                )

        return action

    assert messages(run_together(send(0), send(2))) == [OVERLAP, "ok"]


@pytest.mark.django_db(transaction=True)
def test_undo_of_a_cancellation_races_a_new_request_for_the_same_day(company_a):
    company = Company.objects.get(pk=company_a.company.pk)
    employee = Employee.all_companies.get(pk=company_a.employee.pk)
    telework = company_a.requests["telework"]
    with tenant_context(company):
        result = workflow.cancel(TeleworkRequest.objects.get(pk=telework.pk), employee)
    payload = result.undo_payload("cancel")

    def undo():
        with tenant_context(company):
            return workflow.undo(TeleworkRequest, payload, employee)

    def resend():
        with tenant_context(company):
            return workflow.submit(TeleworkRequest, employee, {"date": telework.date})

    assert messages(run_together(undo, resend)) == [SAME_DAY, "ok"]
    assert (
        TeleworkRequest.all_companies.filter(
            requester=employee, date=telework.date, status="pending"
        ).count()
        == 1
    )


# ---------- c. Alerte de conflit : seulement pour qui décide ----------


def test_requester_never_sees_the_conflict(client_for, company_a, submit):
    leave = company_a.requests["leave"]
    EmployeeFactory(company=company_a.company, service=company_a.service, first_name="Nina")
    colleague = Employee.all_companies.get(first_name="Nina")
    submit(company_a, colleague, LeaveRequest, start=leave.start, end=leave.end)

    own = client_for(company_a.employee).get(f"/conges/{leave.public_id}/").content.decode()
    assert "Nina" not in own and "autre absence" not in own and "autres absences" not in own
    validator = client_for(company_a.manager).get(f"/conges/{leave.public_id}/").content.decode()
    assert "Nina" in validator


def test_submission_toast_does_not_count_the_colleagues_absences(client_for, company_a, submit):
    leave = company_a.requests["leave"]
    colleague = EmployeeFactory(
        company=company_a.company, service=company_a.service, manager=company_a.manager
    )
    response = client_for(colleague).post(
        "/conges/nouvelle/",
        {"start": leave.start.isoformat(), "end": leave.end.isoformat(), "leave_type": "summer"},
    )
    assert response.status_code == 204
    assert "absence" not in toast(response)["message"]


# ---------- e. Notifications devenues fausses ----------


def test_cancellation_within_45_seconds_sends_nothing_to_the_validator(
    company_a, submit, run_tasks
):
    result = submit(company_a, company_a.employee)
    with tenant_context(company_a.company):
        workflow.cancel(result.request, company_a.employee)
    assert not Notification.all_companies.filter(pk__in=result.notification_ids).exists()
    run_tasks(after_seconds=46)
    assert [m for m in mail.outbox if m.to == [company_a.manager.user.email]] == []


def test_refusal_retracts_the_other_validators_notification(company_a, submit, run_tasks):
    Employee.all_companies.filter(pk=company_a.employee.pk).update(manager=None)
    requester = Employee.all_companies.get(pk=company_a.employee.pk)
    result = submit(company_a, requester)  # RH et administrateur sont prévenus
    with tenant_context(company_a.company):
        workflow.refuse(result.request, company_a.hr, reason="Non")
    run_tasks(after_seconds=46)
    assert [m.to for m in mail.outbox] == [[requester.user.email]]


def test_undo_of_a_cancellation_warns_the_validator_again(company_a, submit, run_tasks):
    result = submit(company_a, company_a.employee)
    with tenant_context(company_a.company):
        cancelled = workflow.cancel(result.request, company_a.employee)
        workflow.undo(TeleworkRequest, cancelled.undo_payload("cancel"), company_a.employee)
    run_tasks(after_seconds=46)
    assert [m.to for m in mail.outbox] == [[company_a.manager.user.email]]


def test_hr_cancellation_retracts_the_unsent_validation(company_a, submit, run_tasks):
    request = submit(company_a, company_a.employee).request
    with tenant_context(company_a.company):
        workflow.approve(request, company_a.manager)
        workflow.cancel_approved(request, company_a.hr, reason="Erreur de saisie")
    run_tasks(after_seconds=46)
    subjects = [m.subject for m in mail.outbox if m.to == [company_a.employee.user.email]]
    assert subjects == ["Votre demande de télétravail a été annulée"]


# ---------- f. Campagnes : une seule ouverte, jamais d'erreur 500 ----------


@pytest.mark.django_db(transaction=True)
def test_two_simultaneous_openings_give_one_open_campaign(company_a, client_for):
    SummerCampaign.all_companies.filter(company=company_a.company).update(status="closed")
    drafts = [
        SummerCampaign.all_companies.create(
            company=company_a.company,
            label=label,
            period_start=f"{year}-06-01",
            period_end=f"{year}-09-30",
            deadline=f"{year}-02-28",
        )
        for label, year in (("Été 2028", 2028), ("Été 2029", 2029))
    ]
    hr = Employee.all_companies.get(pk=company_a.hr.pk)
    clients = [client_for(hr), client_for(hr)]
    cookies = clients[0].cookies

    def open_campaign(index):
        def action():
            client = Client(HTTP_HOST=clients[index].defaults["HTTP_HOST"])
            client.cookies = cookies
            return client.post(f"/conges/campagnes/{drafts[index].pk}/ouvrir/")

        return action

    responses = run_together(open_campaign(0), open_campaign(1))
    assert sorted(r.status_code for r in responses) == [204, 409]
    refused = next(r for r in responses if r.status_code == 409)
    assert toast(refused)["title"] == "Une campagne est déjà ouverte."
    opened = SummerCampaign.all_companies.filter(company=company_a.company, status="open")
    assert opened.count() == 1
