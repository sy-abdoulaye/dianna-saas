"""Services de la carrière : étapes, signatures, remplacement du manager, notes privées,
campagnes, compétences et échéances de l'entretien de parcours (docs/modules/10-carriere.md)."""

from datetime import date, timedelta

import pytest
from django.utils import timezone

from apps.careers import selectors, services
from apps.careers.models import (
    Competency,
    FollowUpNote,
    Review,
    ReviewKind,
    ReviewReason,
    ReviewStep,
)
from apps.core.context import ActionContext
from apps.core.models import AuditLog, Notification
from apps.core.tenancy import tenant_context
from tests.factories import EmployeeFactory


@pytest.fixture
def ctx(company_a):
    with tenant_context(company_a.company):
        yield company_a


def as_(person) -> ActionContext:
    return ActionContext(person)


def launch(data, kind=ReviewKind.PROFESSIONAL, reason=ReviewReason.PERIODIC, by=None):
    return services.launch_review(data.employee, kind, reason, context=as_(by or data.manager))


def ratings() -> dict[int, int]:
    return {c.pk: 3 for c in Competency.objects.filter(active=True)}


def evaluation(**changes) -> services.Evaluation:
    values = {
        "summary": "Belle année.",
        "strengths": "Rigueur.",
        "improvements": "Déléguer.",
        "ratings": ratings(),
        "objectives": [("Former un arrivant", date(2031, 6, 30))],
    }
    values.update(changes)
    return services.Evaluation(**values)


# ---------- Lancement ----------


def test_launch_notifies_the_employee_and_refuses_a_second_review_of_the_same_kind(ctx):
    review = launch(ctx)
    assert review.step == ReviewStep.SELF and review.manager == ctx.manager
    assert review.campaign == ctx.requests["review_campaign"]
    note = Notification.objects.get(source_type="review", source_id=review.pk)
    assert note.recipient == ctx.employee and note.email_subject
    with pytest.raises(services.CareerError) as error:
        launch(ctx)
    assert "déjà en cours" in str(error.value.message)


def test_a_manager_cannot_launch_a_review_outside_the_team(ctx):
    stranger = EmployeeFactory(company=ctx.company)
    with pytest.raises(services.CareerError):
        services.launch_review(stranger, "individual", "", context=as_(ctx.manager))


def test_undo_launch_removes_the_review_and_its_notification(ctx):
    review = launch(ctx)
    services.undo_launch(str(review.public_id), context=as_(ctx.manager))
    assert not Review.objects.filter(pk=review.pk).exists()
    assert not Notification.objects.filter(source_type="review", source_id=review.pk).exists()


def test_undo_launch_is_refused_once_the_employee_has_started(ctx):
    review = launch(ctx)
    services.submit_self(review, summary="Mon parcours " * 3, project="", context=as_(ctx.employee))
    with pytest.raises(services.CareerError):
        services.undo_launch(str(review.public_id), context=as_(ctx.manager))


# ---------- Étapes ----------


def test_a_manager_cannot_fill_the_self_assessment(ctx):
    review = launch(ctx)
    with pytest.raises(services.CareerError):
        services.submit_self(review, summary="x" * 30, project="", context=as_(ctx.manager))


def test_evaluation_is_blocked_until_every_competency_is_rated(ctx):
    review = ctx.requests["review"]
    incomplete = ratings()
    incomplete.pop(next(iter(incomplete)))
    with pytest.raises(services.CareerError) as error:
        services.submit_evaluation(review, evaluation(ratings=incomplete), context=as_(ctx.manager))
    assert error.value.field == "ratings"
    done = services.submit_evaluation(review, evaluation(), context=as_(ctx.manager))
    assert done.step == ReviewStep.MEETING and done.ratings.count() == 4


def test_an_employee_cannot_evaluate_and_steps_cannot_be_replayed(ctx):
    review = ctx.requests["review"]
    with pytest.raises(services.CareerError):
        services.submit_evaluation(review, evaluation(), context=as_(ctx.employee))
    services.submit_evaluation(review, evaluation(), context=as_(ctx.manager))
    with pytest.raises(services.CareerError) as error:
        services.submit_evaluation(review, evaluation(), context=as_(ctx.manager))
    assert error.value.message == services.ALREADY_DONE


def test_meeting_date_cannot_be_in_the_past_and_held_only_from_that_date(ctx):
    review = services.submit_evaluation(
        ctx.requests["review"], evaluation(), context=as_(ctx.manager)
    )
    today = timezone.localdate()
    with pytest.raises(services.CareerError) as error:
        services.plan_meeting(
            review, meeting_date=today - timedelta(days=1), place="", context=as_(ctx.manager)
        )
    assert error.value.message == services.PAST_DATE
    services.plan_meeting(
        review, meeting_date=today + timedelta(days=3), place="Salle A", context=as_(ctx.manager)
    )
    with pytest.raises(services.CareerError):
        services.mark_held(review, context=as_(ctx.manager))
    Review.objects.filter(pk=review.pk).update(meeting_date=today)
    held = services.mark_held(review, context=as_(ctx.manager))
    assert held.step == ReviewStep.SIGNATURE and held.held_at


def professional_at_report(data) -> Review:
    review = launch(data, reason=ReviewReason.SUMMARY)
    services.submit_self(
        review, summary="Mon parcours " * 3, project="Évoluer", context=as_(data.employee)
    )
    services.plan_meeting(
        review, meeting_date=timezone.localdate(), place="", context=as_(data.manager)
    )
    return services.mark_held(review, context=as_(data.manager))


def test_professional_review_follows_self_meeting_report_signature(ctx):
    review = professional_at_report(ctx)
    assert review.step == ReviewStep.MANAGER
    report = services.ParcoursReport(
        report="Projet validé.",
        trainings=["ITIL", "Animation"],
        next_review_due=date(2030, 10, 1),
        summary_criteria=(True, None, False),
    )
    review = services.submit_report(review, report, context=as_(ctx.manager))
    assert review.step == ReviewStep.SIGNATURE
    assert (review.summary_training, review.summary_certification, review.summary_progression) == (
        True,
        None,
        False,
    )
    assert list(review.trainings.values_list("label", flat=True)) == ["ITIL", "Animation"]


def at_signature(data) -> Review:
    review = services.submit_evaluation(
        data.requests["review"], evaluation(), context=as_(data.manager)
    )
    services.plan_meeting(
        review, meeting_date=timezone.localdate(), place="", context=as_(data.manager)
    )
    return services.mark_held(review, context=as_(data.manager))


def test_two_signatures_close_the_review_and_add_a_follow_up_note(ctx):
    review = at_signature(ctx)
    services.sign(review, comment="Merci pour l'échange.", context=as_(ctx.employee))
    review = services.sign(review, context=as_(ctx.manager))
    assert review.step == ReviewStep.CLOSED and not review.signed_by_hr
    assert review.employee_comment == "Merci pour l'échange."
    note = FollowUpNote.objects.get(review=review)
    assert note.kind == FollowUpNote.Kind.REVIEW and not note.is_private


def test_nobody_signs_twice_nor_both_sides(ctx):
    review = at_signature(ctx)
    services.sign(review, context=as_(ctx.employee))
    with pytest.raises(services.CareerError):
        services.sign(review, context=as_(ctx.employee))
    review.refresh_from_db()
    assert review.manager_signed_at is None


def test_hr_signs_in_place_of_a_present_manager_with_a_journal_trace(ctx):
    review = at_signature(ctx)
    review = services.sign(review, context=as_(ctx.hr))
    assert review.signed_by_hr and review.manager_signed_by == ctx.hr
    log = AuditLog.objects.filter(action="careers.signed").latest("pk")
    assert f"à la place de {ctx.manager.full_name}" in log.summary


def test_without_a_manager_hr_hold_the_role_and_nobody_signs_his_own_review(ctx):
    review = Review.objects.create(employee=ctx.hr, kind="individual", step="signature")
    assert selectors.acting_manager(review) is None
    assert not selectors.can_act_as_manager(ctx.hr, review)
    assert selectors.can_act_as_manager(ctx.admin, review)
    assert selectors.is_todo(ctx.admin, review)
    with pytest.raises(services.CareerError):
        services.sign(review, context=as_(ctx.manager))


def test_a_manager_who_left_hands_the_review_to_hr(ctx):
    review = ctx.requests["review"]
    ctx.employee.manager = None
    ctx.employee.save()
    review.refresh_from_db()
    assert selectors.acting_manager(review) is None
    assert not selectors.can_act_as_manager(ctx.manager, review)
    assert selectors.is_todo(ctx.hr, review)


def test_hr_to_do_only_shows_people_without_manager(ctx):
    review = ctx.requests["review"]
    assert selectors.is_todo(ctx.manager, review)
    assert not selectors.is_todo(ctx.hr, review)
    assert selectors.can_act_as_manager(ctx.hr, review)
    assert selectors.replaced_manager(ctx.hr, review) == ctx.manager


def test_remind_notifies_the_expected_people_once_a_day(ctx):
    review = ctx.requests["review"]
    review.step = ReviewStep.SELF
    review.save()
    assert services.remind(review, context=as_(ctx.manager)) == 1
    with pytest.raises(services.CareerError):
        services.remind(review, context=as_(ctx.hr))
    with pytest.raises(services.CareerError):
        services.remind(review, context=as_(ctx.employee))


# ---------- Notes de suivi ----------


def test_a_private_note_is_visible_by_its_author_only(ctx):
    private = ctx.requests["private_note"]
    other_manager = EmployeeFactory(company=ctx.company, role="manager")
    EmployeeFactory(company=ctx.company, manager=other_manager)
    for viewer in (ctx.employee, ctx.hr, ctx.admin, other_manager):
        assert private not in selectors.visible_notes(viewer, ctx.employee)
    assert private in selectors.visible_notes(ctx.manager, ctx.employee)
    assert private not in selectors.public_notes(ctx.employee)


def test_another_manager_sees_no_note_of_a_person_outside_his_team(ctx):
    other_manager = EmployeeFactory(company=ctx.company, role="manager")
    EmployeeFactory(company=ctx.company, manager=other_manager)
    assert not selectors.visible_notes(other_manager, ctx.employee).exists()


def test_an_employee_writes_only_wishes_on_his_own_file(ctx):
    with pytest.raises(services.CareerError):
        services.add_note(
            ctx.employee,
            kind="follow_up",
            text="Je voudrais un point.",
            is_private=False,
            context=as_(ctx.employee),
        )
    with pytest.raises(services.CareerError):
        services.add_note(
            ctx.employee,
            kind="wish",
            text="Mon souhait.",
            is_private=True,
            context=as_(ctx.employee),
        )
    note = services.add_note(
        ctx.employee,
        kind="wish",
        text="Évoluer vers le niveau 2.",
        is_private=False,
        context=as_(ctx.employee),
    )
    assert note.author == ctx.employee


def test_an_employee_cannot_add_a_note_on_a_colleague(ctx):
    with pytest.raises(services.CareerError):
        services.add_note(
            ctx.manager,
            kind="wish",
            text="Un souhait.",
            is_private=False,
            context=as_(ctx.employee),
        )


def test_undo_note_is_reserved_to_its_author(ctx):
    note = services.add_note(
        ctx.employee,
        kind="follow_up",
        text="Point du jour.",
        is_private=True,
        context=as_(ctx.manager),
    )
    with pytest.raises(services.CareerError):
        services.undo_note(note.pk, context=as_(ctx.hr))
    services.undo_note(note.pk, context=as_(ctx.manager))
    assert not FollowUpNote.objects.filter(pk=note.pk).exists()


# ---------- Campagnes et compétences ----------


def test_campaigns_cannot_overlap(ctx):
    current = ctx.requests["review_campaign"]
    with pytest.raises(services.CareerError) as error:
        services.save_campaign(
            {"label": "Autre", "start": current.start, "end": current.end},
            context=as_(ctx.hr),
        )
    assert error.value.field == "start"
    updated = services.save_campaign(
        {"label": "Campagne 2026", "start": current.start, "end": current.end},
        campaign=current,
        context=as_(ctx.hr),
    )
    assert updated.label == "Campagne 2026"


def test_competencies_are_added_renamed_moved_and_deactivated(ctx):
    added = services.add_competency("Pédagogie", "Transmettre", context=as_(ctx.admin))
    assert added.order == 5
    with pytest.raises(services.CareerError) as error:
        services.add_competency("pédagogie", "", context=as_(ctx.admin))
    assert error.value.field == "name"
    assert services.move_competency(added, -1, context=as_(ctx.admin))
    names = list(Competency.objects.values_list("name", flat=True))
    assert names[3] == "Pédagogie"
    services.set_competency_active(added, False, context=as_(ctx.admin))
    assert added not in selectors.active_competencies()
    assert not services.move_competency(Competency.objects.first(), -1, context=as_(ctx.admin))


def test_the_last_active_competency_cannot_be_deactivated(ctx):
    *others, last = list(Competency.objects.all())
    for competency in others:
        services.set_competency_active(competency, False, context=as_(ctx.admin))
    with pytest.raises(services.CareerError):
        services.set_competency_active(last, False, context=as_(ctx.admin))


# ---------- Échéances (M-08, à confirmer par un juriste) ----------


def test_first_review_is_due_within_the_first_year_and_summary_after_eight(ctx):
    person = EmployeeFactory(company=ctx.company, arrival_date=date(2024, 3, 15))
    assert selectors.suggested_dues(person) == (date(2025, 3, 15), date(2032, 3, 15))


def test_next_review_is_due_four_years_after_the_last_one_held(ctx):
    person = EmployeeFactory(company=ctx.company, arrival_date=date(2020, 1, 6))
    Review.objects.create(
        employee=person,
        kind="professional",
        reason="periodic",
        step="closed",
        meeting_date=date(2025, 5, 20),
        closed_at=timezone.now(),
    )
    review_due, summary_due = selectors.suggested_dues(person)
    assert review_due == date(2029, 5, 20) and summary_due == date(2028, 1, 6)


def test_a_due_date_entered_on_the_last_review_wins(ctx):
    person = EmployeeFactory(company=ctx.company, arrival_date=date(2020, 1, 6))
    Review.objects.create(
        employee=person,
        kind="professional",
        reason="summary",
        step="closed",
        meeting_date=date(2026, 2, 1),
        next_review_due=date(2028, 2, 1),
        closed_at=timezone.now(),
    )
    assert selectors.suggested_dues(person) == (date(2028, 2, 1), date(2034, 2, 1))
