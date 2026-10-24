"""Moteur commun des demandes : transitions, effets, valideurs, annulation immédiate."""

import threading

import pytest
from django.core import mail
from django.db import connection

from apps.agenda.models import CalendarEvent
from apps.approvals import workflow
from apps.approvals.models import (
    LeaveRequest,
    OnCallDeclaration,
    RequestEvent,
    RequestStatus,
    TeleworkRequest,
)
from apps.core.context import ActionContext
from apps.core.models import AuditLog, Company, Notification
from apps.core.tenancy import tenant_context
from apps.people.models import Employee, Role
from tests.factories import EmployeeFactory

pytestmark = pytest.mark.django_db


def events(request):
    return list(
        RequestEvent.all_companies.filter(
            request_type=request.request_type, request_id=request.pk
        ).values_list("action", flat=True)
    )


def calendar(request):
    return CalendarEvent.all_companies.filter(
        source_type=request.request_type, source_id=request.pk
    ).first()


def audits(company_data):
    return list(
        AuditLog.all_companies.filter(company=company_data.company).values_list("action", flat=True)
    )


def test_submit_creates_pending_request_event_calendar_and_notifies_the_manager(
    company_a, submit, run_tasks
):
    result = submit(company_a, company_a.employee)
    request = result.request
    assert request.status == RequestStatus.PENDING
    assert events(request) == ["submitted"]
    assert calendar(request).status == CalendarEvent.Status.PENDING
    note = Notification.all_companies.get(pk=result.notification_ids[0])
    assert note.recipient == company_a.manager
    assert "télétravail à valider" in note.text
    assert "requests.submitted" in audits(company_a)
    run_tasks()
    assert mail.outbox == []  # e-mail différé de 45 s
    run_tasks(after_seconds=46)
    assert mail.outbox[-1].to == [company_a.manager.user.email]
    assert "Demande à valider : télétravail" in mail.outbox[-1].subject


def test_manager_approves_once_even_with_two_clicks(company_a, submit):
    request = submit(company_a, company_a.employee).request
    with tenant_context(company_a.company):
        workflow.approve(request, context=ActionContext(company_a.manager))
        with pytest.raises(workflow.WorkflowError) as error:
            workflow.approve(request, context=ActionContext(company_a.manager))
    assert str(error.value.message) == "Cette demande a déjà été traitée."
    request.refresh_from_db()
    assert request.status == RequestStatus.APPROVED and request.decided_by == company_a.manager
    assert calendar(request).status == CalendarEvent.Status.APPROVED
    assert events(request) == ["submitted", "approved"]


@pytest.mark.django_db(transaction=True)
def test_two_simultaneous_validations_make_a_single_transition(company_a, submit):
    request = submit(company_a, company_a.employee).request
    company = Company.objects.get(pk=company_a.company.pk)
    manager = Employee.all_companies.get(pk=company_a.manager.pk)
    barrier = threading.Barrier(2)
    outcomes = []

    def validate():
        try:
            with tenant_context(company):
                barrier.wait()
                workflow.approve(
                    TeleworkRequest.objects.get(pk=request.pk), context=ActionContext(manager)
                )
                outcomes.append("ok")
        except workflow.WorkflowError:
            outcomes.append("déjà traitée")
        finally:
            connection.close()

    threads = [threading.Thread(target=validate) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(outcomes) == ["déjà traitée", "ok"]
    assert events(TeleworkRequest.all_companies.get(pk=request.pk)).count("approved") == 1


def test_refusal_needs_a_reason_removes_the_event_and_tells_the_requester(company_a, submit):
    request = submit(company_a, company_a.employee).request
    with tenant_context(company_a.company):
        with pytest.raises(workflow.WorkflowError):
            workflow.refuse(request, reason="  ", context=ActionContext(company_a.manager))
        result = workflow.refuse(
            request, reason="Réunion d'équipe", context=ActionContext(company_a.manager)
        )
    assert calendar(request) is None
    assert RequestEvent.all_companies.filter(
        request_id=request.pk, action="refused", comment="Réunion d'équipe"
    ).exists()
    note = Notification.all_companies.get(pk=result.notification_ids[0])
    assert note.recipient == company_a.employee and "Réunion d'équipe" in note.text


def test_nobody_decides_for_themselves_or_outside_their_scope(company_a, submit):
    request = submit(company_a, company_a.manager).request  # Louise n'a pas de manager
    other = EmployeeFactory(company=company_a.company, user=None)
    with tenant_context(company_a.company):
        assert not workflow.can_decide(company_a.manager, request)
        assert not workflow.can_decide(other, request)
        assert workflow.can_decide(company_a.hr, request)


def test_hr_can_act_for_the_manager_and_it_is_traced(company_a, submit):
    request = submit(company_a, company_a.employee).request
    with tenant_context(company_a.company):
        assert workflow.acting_for(company_a.hr, request) == company_a.manager
        workflow.approve(request, context=ActionContext(company_a.hr))
        entry = AuditLog.objects.filter(action="requests.approved").first()
    assert f"à la place de {company_a.manager.full_name}" in entry.summary


def test_to_validate_tabs(company_a, submit):
    team_request = submit(company_a, company_a.employee).request
    orphan_request = submit(company_a, company_a.manager).request  # sans manager
    with tenant_context(company_a.company):
        manager_list = list(workflow.to_validate(company_a.manager, TeleworkRequest))
        hr_list = list(workflow.to_validate(company_a.hr, TeleworkRequest))
    fixture_request = company_a.requests["telework"]  # en attente, même salariée
    assert set(manager_list) == {team_request, fixture_request}
    assert hr_list == [orphan_request]  # M-12 : seulement les personnes sans manager


def test_without_manager_the_request_goes_to_hr_and_admins(company_a, submit):
    result = submit(company_a, company_a.manager)
    recipients = set(
        Notification.all_companies.filter(pk__in=result.notification_ids).values_list(
            "recipient_id", flat=True
        )
    )
    assert recipients == {company_a.hr.pk, company_a.admin.pk}


def test_no_validator_at_all_means_automatic_approval(company_a, submit):
    Employee.all_companies.filter(
        company=company_a.company, role__in=(Role.HR, Role.ADMIN)
    ).exclude(pk=company_a.admin.pk).update(role=Role.EMPLOYEE)
    result = submit(company_a, company_a.admin)  # seul RH/admin, sans manager
    request = result.request
    assert result.auto_approved and request.status == RequestStatus.APPROVED
    assert calendar(request).status == CalendarEvent.Status.APPROVED
    entry = AuditLog.all_companies.get(action="requests.auto_approved")
    assert "validation automatique : aucun valideur disponible" in entry.summary


def test_telework_auto_approval_option(company_a, submit):
    Company.objects.filter(pk=company_a.company.pk).update(telework_auto_approve=True)
    company_a.company.refresh_from_db()
    company_a.employee.company.refresh_from_db()
    result = submit(company_a, Employee.all_companies.get(pk=company_a.employee.pk))
    assert result.auto_approved and result.request.status == RequestStatus.APPROVED
    assert "auto_approved" in events(result.request)


# ---------- Congés d'été et étape RH (M-03, L3-02, L3-03) ----------


def test_summer_leave_goes_through_manager_then_hr(company_a, submit):
    request = submit(company_a, company_a.employee, LeaveRequest).request
    with tenant_context(company_a.company):
        result = workflow.approve(request, context=ActionContext(company_a.manager))
        request.refresh_from_db()
        assert request.status == RequestStatus.MANAGER_APPROVED
        assert calendar(request).status == CalendarEvent.Status.PENDING  # hachuré
        hr_notes = Notification.objects.filter(
            pk__in=result.notification_ids, recipient=company_a.hr
        )
        assert hr_notes.exists()
        assert request in workflow.to_validate(company_a.hr, LeaveRequest)
        assert not workflow.can_decide(company_a.manager, request)
        workflow.approve(request, context=ActionContext(company_a.hr))
    request.refresh_from_db()
    assert request.status == RequestStatus.APPROVED
    assert request.manager_decided_by == company_a.manager and request.decided_by == company_a.hr
    assert calendar(request).status == CalendarEvent.Status.APPROVED


def test_without_hr_step_the_manager_decision_is_final(company_a, submit):
    Company.objects.filter(pk=company_a.company.pk).update(summer_leave_hr_step=False)
    request = submit(company_a, company_a.employee, LeaveRequest).request
    request.company.refresh_from_db()
    with tenant_context(company_a.company):
        workflow.approve(
            LeaveRequest.objects.get(pk=request.pk), context=ActionContext(company_a.manager)
        )
    assert LeaveRequest.all_companies.get(pk=request.pk).status == RequestStatus.APPROVED


def test_other_absence_is_validated_by_the_manager_alone(company_a, submit):
    request = submit(
        company_a, company_a.employee, LeaveRequest, leave_type="other", campaign=None
    ).request
    with tenant_context(company_a.company):
        workflow.approve(request, context=ActionContext(company_a.manager))
    assert LeaveRequest.all_companies.get(pk=request.pk).status == RequestStatus.APPROVED


def test_no_manager_with_hr_step_means_a_single_hr_validation(company_a, submit):
    request = submit(company_a, company_a.manager, LeaveRequest).request  # L3-02
    with tenant_context(company_a.company):
        workflow.approve(request, context=ActionContext(company_a.hr))
    assert LeaveRequest.all_companies.get(pk=request.pk).status == RequestStatus.APPROVED


def test_hr_manager_decision_is_final(company_a, submit):
    Employee.all_companies.filter(pk=company_a.employee.pk).update(manager=company_a.hr)
    request = submit(
        company_a, Employee.all_companies.get(pk=company_a.employee.pk), LeaveRequest
    ).request
    with tenant_context(company_a.company):
        workflow.approve(request, context=ActionContext(company_a.hr))  # L3-03
    assert LeaveRequest.all_companies.get(pk=request.pk).status == RequestStatus.APPROVED


def test_intervention_is_not_projected_but_on_call_is(company_a, submit):
    on_call = submit(company_a, company_a.employee, OnCallDeclaration).request
    intervention = submit(
        company_a, company_a.employee, OnCallDeclaration, kind="intervention", hours=3
    ).request
    assert calendar(on_call) is not None and calendar(intervention) is None


# ---------- Annulations ----------


def test_requester_cancels_a_pending_request_only(company_a, submit):
    request = submit(company_a, company_a.employee).request
    with tenant_context(company_a.company):
        with pytest.raises(workflow.WorkflowError):
            workflow.cancel(request, context=ActionContext(company_a.manager))
        workflow.cancel(request, context=ActionContext(company_a.employee))
        request.refresh_from_db()
        assert request.status == RequestStatus.CANCELLED and calendar(request) is None
        approved = submit(company_a, company_a.employee).request
        workflow.approve(approved, context=ActionContext(company_a.manager))
        with pytest.raises(workflow.WorkflowError):
            workflow.cancel(approved, context=ActionContext(company_a.employee))


def test_hr_cancels_an_approved_request_with_a_reason(company_a, submit, run_tasks):
    request = submit(company_a, company_a.employee).request
    with tenant_context(company_a.company):
        workflow.approve(request, context=ActionContext(company_a.manager))
        with pytest.raises(workflow.WorkflowError):
            workflow.cancel_approved(request, reason="", context=ActionContext(company_a.hr))
        with pytest.raises(workflow.WorkflowError):
            workflow.cancel_approved(
                request, reason="Fermeture", context=ActionContext(company_a.manager)
            )
        result = workflow.cancel_approved(
            request, reason="Fermeture du site", context=ActionContext(company_a.hr)
        )
    request.refresh_from_db()
    assert request.status == RequestStatus.CANCELLED and calendar(request) is None
    note = Notification.all_companies.get(pk=result.notification_ids[0])
    assert note.recipient == company_a.employee and "Fermeture du site" in note.text
    run_tasks(after_seconds=46)
    assert any("annulée" in m.subject for m in mail.outbox)
    assert "requests.cancelled_approved" in audits(company_a)


# ---------- Annulation immédiate ----------


def test_undo_submit_removes_everything_and_keeps_an_audit_line(company_a, submit, run_tasks):
    result = submit(company_a, company_a.employee)
    request = result.request
    with tenant_context(company_a.company):
        workflow.undo(
            TeleworkRequest,
            result.undo_payload("submit"),
            context=ActionContext(company_a.employee),
        )
    assert not TeleworkRequest.all_companies.filter(pk=request.pk).exists()
    assert calendar(request) is None
    assert not Notification.all_companies.filter(pk__in=result.notification_ids).exists()
    assert "requests.withdrawn" in audits(company_a)
    run_tasks(after_seconds=46)
    assert mail.outbox == []


def test_undo_approval_restores_pending_and_cancels_the_email(company_a, submit, run_tasks):
    request = submit(company_a, company_a.employee).request
    with tenant_context(company_a.company):
        result = workflow.approve(request, context=ActionContext(company_a.manager))
        workflow.undo(
            TeleworkRequest,
            result.undo_payload("approve"),
            context=ActionContext(company_a.manager),
        )
    request.refresh_from_db()
    assert request.status == RequestStatus.PENDING and request.decided_by is None
    assert calendar(request).status == CalendarEvent.Status.PENDING
    assert events(request)[-1] == "reverted"
    mail.outbox.clear()
    run_tasks(after_seconds=46)
    # Seul l'e-mail « à valider » au manager part ; celui de la décision a été annulé.
    assert all("validée" not in m.subject for m in mail.outbox)


def test_undo_refusal_recreates_the_calendar_event(company_a, submit):
    request = submit(company_a, company_a.employee).request
    with tenant_context(company_a.company):
        result = workflow.refuse(request, reason="Non", context=ActionContext(company_a.manager))
        workflow.undo(
            TeleworkRequest, result.undo_payload("refuse"), context=ActionContext(company_a.manager)
        )
    assert calendar(request).status == CalendarEvent.Status.PENDING
