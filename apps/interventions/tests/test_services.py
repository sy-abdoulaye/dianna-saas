"""Services du suivi d'intervention : enregistrement versionné, doublon, envoi, décisions,
annulation immédiate et valideurs (docs/modules/11-interventions.md, M-11, M-12)."""

from datetime import date

import pytest

from apps.core.context import ActionContext
from apps.core.models import AuditLog, Notification
from apps.core.tenancy import tenant_context
from apps.interventions import selectors, services
from apps.interventions.models import InterventionReport, ReportEvent, ReportStatus
from tests.factories import EmployeeFactory


@pytest.fixture
def ctx(company_a):
    with tenant_context(company_a.company):
        yield company_a


def as_(person) -> ActionContext:
    return ActionContext(person)


def data(**changes) -> services.ReportData:
    values = {
        "mission": "Refonte de l'espace client",
        "period": date(2026, 9, 1),
        "visibility": "uncertain",
        "planned_end": date(2026, 11, 30),
        "done": [services.ItemData(description="Module de paiement", completion=60)],
        "next": [services.ItemData(description="Tests de bout en bout", completion=0)],
    }
    values.update(changes)
    return services.ReportData(**values)


def draft(person, **changes) -> InterventionReport:
    return services.save_report(None, data(**changes), version=None, context=as_(person))


def test_a_draft_needs_only_the_intervention_and_the_period(ctx):
    report = draft(ctx.employee, visibility="", planned_end=None, done=[], next=[])
    assert report.status == ReportStatus.DRAFT and report.version == 1
    assert report.mission.name == "Refonte de l'espace client"


def test_an_existing_intervention_is_reused_whatever_the_case(ctx):
    report = draft(ctx.employee, mission="SUPPORT NIVEAU 2 · CONTRAT ATLAS")
    assert report.mission == ctx.requests["mission"]


def test_one_report_per_intervention_and_period(ctx):
    draft(ctx.employee)
    with pytest.raises(services.ReportError) as error:
        draft(ctx.employee)
    assert error.value.message == services.DUPLICATE and error.value.field == "period"


def test_a_stale_version_never_overwrites_the_report(ctx):
    report = draft(ctx.employee)
    services.save_report(report, data(follow_up="Onglet A"), version=1, context=as_(ctx.employee))
    with pytest.raises(services.ReportError) as error:
        services.save_report(
            report, data(follow_up="Onglet B"), version=1, context=as_(ctx.employee)
        )
    assert error.value.message == services.STALE
    report.refresh_from_db()
    assert report.follow_up == "Onglet A" and report.version == 2


def test_only_the_author_saves_and_only_while_editable(ctx):
    report = draft(ctx.employee)
    with pytest.raises(services.ReportError):
        services.save_report(report, data(), version=1, context=as_(ctx.manager))
    services.submit(report, context=as_(ctx.employee))
    with pytest.raises(services.ReportError) as error:
        services.save_report(report, data(), version=None, context=as_(ctx.employee))
    assert error.value.message == services.NOT_EDITABLE


def test_an_incomplete_report_cannot_be_sent(ctx):
    report = draft(ctx.employee, done=[])
    with pytest.raises(services.ReportError) as error:
        services.submit(report, context=as_(ctx.employee))
    assert error.value.message == services.INCOMPLETE


def test_sending_notifies_the_manager_who_validates_and_the_author_is_notified(ctx):
    report = draft(ctx.employee)
    sent = services.submit(report, context=as_(ctx.employee))
    assert sent.report.status == ReportStatus.SUBMITTED
    note = Notification.objects.get(pk=sent.notification_ids[0])
    assert note.recipient == ctx.manager and note.email_subject == "Compte rendu à valider"
    assert report in selectors.to_validate(ctx.manager)
    decided = services.decide(report, approve=True, note="Merci.", context=as_(ctx.manager))
    assert decided.report.status == ReportStatus.APPROVED
    assert report not in selectors.to_validate(ctx.manager)
    assert Notification.objects.filter(recipient=ctx.employee, source_id=report.pk).exists()


def test_asking_for_changes_needs_a_remark_and_reopens_the_report(ctx):
    report = draft(ctx.employee)
    services.submit(report, context=as_(ctx.employee))
    with pytest.raises(services.ReportError) as error:
        services.decide(report, approve=False, note=" ", context=as_(ctx.manager))
    assert error.value.field == "note"
    services.decide(report, approve=False, note="Précise le risque.", context=as_(ctx.manager))
    report.refresh_from_db()
    assert report.status == ReportStatus.CHANGES_REQUESTED and report.is_editable
    assert report.reviewer_note == "Précise le risque."


def test_nobody_decides_on_his_own_report_nor_twice(ctx):
    report = draft(ctx.employee)
    services.submit(report, context=as_(ctx.employee))
    with pytest.raises(services.ReportError):
        services.decide(report, approve=True, note="", context=as_(ctx.employee))
    services.decide(report, approve=True, note="", context=as_(ctx.manager))
    with pytest.raises(services.ReportError) as error:
        services.decide(report, approve=True, note="", context=as_(ctx.hr))
    assert error.value.message == services.ALREADY_PROCESSED


def test_hr_validates_in_place_of_the_manager_with_a_journal_trace(ctx):
    report = draft(ctx.employee)
    services.submit(report, context=as_(ctx.employee))
    assert report not in selectors.to_validate(ctx.hr)  # la personne a un manager (M-12)
    assert selectors.replaced_manager(ctx.hr, report) == ctx.manager
    services.decide(report, approve=True, note="", context=as_(ctx.hr))
    log = AuditLog.objects.filter(action="interventions.approved").latest("pk")
    assert f"à la place de {ctx.manager.full_name}" in log.summary


def test_without_a_manager_the_report_goes_to_hr(ctx):
    alone = EmployeeFactory(company=ctx.company)
    report = draft(alone)
    sent = services.submit(report, context=as_(alone))
    recipients = set(
        Notification.objects.filter(pk__in=sent.notification_ids).values_list(
            "recipient", flat=True
        )
    )
    assert recipients == {ctx.hr.pk, ctx.admin.pk}
    assert report in selectors.to_validate(ctx.hr)


def test_undo_a_send_brings_back_the_draft_without_trace(ctx):
    report = draft(ctx.employee)
    sent = services.submit(report, context=as_(ctx.employee))
    services.undo(sent.undo_payload(), context=as_(ctx.employee))
    report.refresh_from_db()
    assert report.status == ReportStatus.DRAFT and not report.events.exists()
    assert not Notification.objects.filter(pk__in=sent.notification_ids).exists()


def test_undo_a_decision_is_refused_once_another_action_followed(ctx):
    report = draft(ctx.employee)
    services.submit(report, context=as_(ctx.employee))
    decided = services.decide(report, approve=False, note="À compléter.", context=as_(ctx.manager))
    services.undo(decided.undo_payload(), context=as_(ctx.manager))
    report.refresh_from_db()
    assert report.status == ReportStatus.SUBMITTED
    assert report.events.last().action == ReportEvent.Action.REVERTED
    with pytest.raises(services.ReportError) as error:
        services.undo(decided.undo_payload(), context=as_(ctx.manager))
    assert error.value.message == services.OTHER_DECISION


def test_late_marker_and_average_completion(ctx):
    report = draft(
        ctx.employee,
        done=[
            services.ItemData(description="A", completion=100, due_date=date(2026, 1, 5)),
            services.ItemData(description="B", completion=50, due_date=date(2026, 1, 5)),
        ],
    )
    late = [
        selectors.is_late(item, date(2026, 2, 1)) for item in report.items.filter(section="done")
    ]
    assert late == [False, True]
    assert selectors.average_completion(report) == 75


def test_suggestions_only_show_the_person_own_interventions(ctx):
    draft(ctx.manager, mission="Projet confidentiel")
    assert "Projet confidentiel" not in selectors.missions_of(ctx.employee)
    assert "Support niveau 2 · contrat Atlas" in selectors.missions_of(ctx.employee)
