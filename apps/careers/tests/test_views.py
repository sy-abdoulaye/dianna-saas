"""Écrans de la carrière : critères d'acceptation de docs/modules/10-carriere.md, permissions,
annulation immédiate, blocs répétables et exports PDF."""

import json
import re

import pytest

from apps.careers.models import Competency, FollowUpNote, Review, ReviewStep
from apps.core.models import AuditLog, CompanyModule, Notification
from apps.core.tenancy import tenant_context
from tests.factories import EmployeeFactory

pytestmark = pytest.mark.django_db

HX = {"HX-Request": "true"}


def trigger(response) -> dict:
    return json.loads(response["HX-Trigger"])


def review_of(data) -> Review:
    return data.requests["review"]


def url(review, action="detail") -> str:
    suffix = {
        "detail": "",
        "self": "auto-evaluation/",
        "evaluate": "evaluation/",
        "plan": "planifier/",
        "sign": "signer/",
        "remind": "relancer/",
        "pdf": "pdf/",
    }[action]
    return f"/carriere/{review.public_id}/{suffix}"


def ratings_post(company) -> dict:
    with tenant_context(company):
        return {f"rating_{c.pk}": "3" for c in Competency.objects.filter(active=True)}


def evaluation_post(company, **changes) -> dict:
    data = {
        "summary": "Belle année, beaucoup de progrès.",
        "strengths": "Rigueur.",
        "improvements": "Déléguer.",
        "objectives-TOTAL_FORMS": "1",
        "objectives-INITIAL_FORMS": "0",
        "objectives-0-title": "Former un nouvel arrivant",
        "objectives-0-due_date": "2031-06-30",
        **ratings_post(company),
    }
    data.update(changes)
    return data


# ---------- Visibilité ----------


def test_an_employee_sees_only_his_reviews_and_a_colleague_review_is_404(client_for, company_a):
    colleague = EmployeeFactory(company=company_a.company, manager=company_a.manager)
    with tenant_context(company_a.company):
        other = Review.objects.create(employee=colleague, kind="individual")
    client = client_for(company_a.employee)
    assert client.get(url(review_of(company_a))).status_code == 200
    assert client.get(url(other)).status_code == 404
    assert client.get(url(other, "pdf")).status_code == 404
    page = client.get("/carriere/").content.decode()
    assert colleague.full_name not in page and "Ma fiche de suivi" in page
    assert "Lancer un entretien" not in page


def test_a_manager_sees_the_team_and_hr_the_whole_company(client_for, company_a):
    stranger = EmployeeFactory(company=company_a.company, last_name="Inconnue")
    with tenant_context(company_a.company):
        Review.objects.create(employee=stranger, kind="individual")
    assert "Inconnue" not in client_for(company_a.manager).get("/carriere/").content.decode()
    assert "Inconnue" in client_for(company_a.hr).get("/carriere/").content.decode()


def test_the_module_can_be_disabled(client_for, company_a):
    with tenant_context(company_a.company):
        CompanyModule.objects.update_or_create(module="careers", defaults={"enabled": False})
    response = client_for(company_a.employee).get("/carriere/")
    assert "Module désactivé" in response.content.decode()


# ---------- Lancement et annulation ----------


def test_launching_then_undo_removes_the_review_and_its_notification(client_for, company_a):
    client = client_for(company_a.manager)
    response = client.post(
        "/carriere/lancer/",
        {"employee": company_a.employee.pk, "kind": "professional", "reason": "periodic"},
        headers=HX,
    )
    assert response.status_code == 204
    toast = trigger(response)["toast"]
    assert toast["title"] == "Entretien lancé" and toast["undo_url"]
    with tenant_context(company_a.company):
        review = Review.objects.get(employee=company_a.employee, kind="professional", step="self")
        assert Notification.objects.filter(source_type="review", source_id=review.pk).exists()
    undone = client.post(toast["undo_url"], headers=HX)
    assert trigger(undone)["toast"]["title"] == "Lancement annulé"
    with tenant_context(company_a.company):
        assert not Review.objects.filter(pk=review.pk).exists()
        assert not Notification.objects.filter(source_type="review", source_id=review.pk).exists()


def test_launching_a_second_review_of_the_same_kind_is_refused(client_for, company_a):
    response = client_for(company_a.manager).post(
        "/carriere/lancer/",
        {"employee": company_a.employee.pk, "kind": "individual"},
        headers=HX,
    )
    assert response.status_code == 422
    assert "Un entretien de ce type est déjà en cours" in response.content.decode()


def test_a_professional_review_needs_a_reason(client_for, company_a):
    response = client_for(company_a.manager).post(
        "/carriere/lancer/", {"employee": company_a.employee.pk, "kind": "professional"}, headers=HX
    )
    assert "Choisissez le motif" in response.content.decode()


def test_an_employee_cannot_launch_nor_manage_campaigns(client_for, company_a):
    client = client_for(company_a.employee)
    assert client.get("/carriere/lancer/").status_code == 403
    assert client.get("/carriere/campagne/").status_code == 403


# ---------- Étapes ----------


def test_a_manager_cannot_fill_the_self_assessment(client_for, company_a):
    review = review_of(company_a)
    Review.all_companies.filter(pk=review.pk).update(step=ReviewStep.SELF, self_summary="")
    response = client_for(company_a.manager).post(
        url(review, "self"), {"summary": "Je remplis à sa place " * 2}, headers=HX
    )
    assert response.status_code == 422
    assert Review.all_companies.get(pk=review.pk).step == ReviewStep.SELF


def test_self_assessment_needs_twenty_characters(client_for, company_a):
    review = review_of(company_a)
    Review.all_companies.filter(pk=review.pk).update(step=ReviewStep.SELF, self_summary="")
    client = client_for(company_a.employee)
    short = client.post(url(review, "self"), {"summary": "Trop court"}, headers=HX)
    assert "au moins 20 caractères" in short.content.decode()
    done = client.post(
        url(review, "self"), {"summary": "Une année riche et formatrice."}, headers=HX
    )
    assert done.status_code == 204 and trigger(done)["pageChanged"]
    assert Review.all_companies.get(pk=review.pk).step == ReviewStep.MANAGER


def test_evaluation_is_blocked_until_the_four_competencies_are_rated(client_for, company_a):
    review = review_of(company_a)
    data = evaluation_post(company_a.company)
    data.pop(next(key for key in data if key.startswith("rating_")))
    client = client_for(company_a.manager)
    refused = client.post(url(review, "evaluate"), data, headers=HX)
    assert refused.status_code == 422
    assert "Notez toutes les compétences de 1 à 4." in refused.content.decode()
    assert "Former un nouvel arrivant" in refused.content.decode()  # rien n'est perdu
    done = client.post(url(review, "evaluate"), evaluation_post(company_a.company), headers=HX)
    assert done.status_code == 204
    with tenant_context(company_a.company):
        saved = Review.objects.get(pk=review.pk)
        assert saved.step == ReviewStep.MEETING and saved.objectives.count() == 1


def test_evaluation_needs_at_least_one_objective(client_for, company_a):
    data = evaluation_post(
        company_a.company, **{"objectives-0-title": "", "objectives-0-due_date": ""}
    )
    response = client_for(company_a.manager).post(
        url(review_of(company_a), "evaluate"), data, headers=HX
    )
    assert "Indiquez au moins un objectif." in response.content.decode()


def test_hr_acting_for_a_present_manager_sees_the_banner(client_for, company_a):
    page = client_for(company_a.hr).get(url(review_of(company_a))).content.decode()
    assert f"Vous agissez à la place de {company_a.manager.full_name}." in page


def test_the_employee_waits_for_the_manager_and_cannot_remind(client_for, company_a):
    page = client_for(company_a.employee).get(url(review_of(company_a))).content.decode()
    assert f"En attente de {company_a.manager.full_name}." in page
    assert "Relancer" not in page


def test_a_reminder_goes_once_a_day(client_for, company_a):
    review = review_of(company_a)
    Review.all_companies.filter(pk=review.pk).update(step=ReviewStep.SELF)
    client = client_for(company_a.manager)
    assert trigger(client.post(url(review, "remind"), headers=HX))["toast"]["title"] == (
        "Relance envoyée"
    )
    again = client.post(url(review, "remind"), headers=HX)
    assert again.status_code == 409 and "24 heures" in trigger(again)["toast"]["title"]


def test_signing_closes_the_review_and_adds_a_note(client_for, company_a):
    review = review_of(company_a)
    Review.all_companies.filter(pk=review.pk).update(step=ReviewStep.SIGNATURE)
    employee = client_for(company_a.employee)
    assert "Votre commentaire" in employee.get(url(review, "sign")).content.decode()
    employee.post(url(review, "sign"), {"comment": "Merci."}, headers=HX)
    closed = client_for(company_a.manager).post(url(review, "sign"), headers=HX)
    assert trigger(closed)["toast"]["title"] == "Entretien clos"
    with tenant_context(company_a.company):
        assert FollowUpNote.objects.filter(review=review, kind="review").exists()


# ---------- Fiches de suivi ----------


def test_a_private_note_is_shown_to_its_author_only(client_for, company_a):
    private = company_a.requests["private_note"].text
    file_url = f"/carriere/fiche/{company_a.employee.public_id}/"
    assert private in client_for(company_a.manager).get(file_url).content.decode()
    for person in (company_a.employee, company_a.hr, company_a.admin):
        assert private not in client_for(person).get(file_url).content.decode()


def test_a_colleague_file_is_404(client_for, company_a):
    response = client_for(company_a.employee).get(f"/carriere/fiche/{company_a.manager.public_id}/")
    assert response.status_code == 404


def test_an_employee_can_only_note_a_wish_on_his_file(client_for, company_a):
    note_url = f"/carriere/fiche/{company_a.employee.public_id}/note/"
    client = client_for(company_a.employee)
    modal = client.get(note_url).content.decode()
    assert "Souhait salarié" in modal and "Point de suivi" not in modal
    assert "Note privée" not in modal
    refused = client.post(note_url, {"kind": "follow_up", "text": "Un point de suivi."}, headers=HX)
    assert refused.status_code == 422
    done = client.post(note_url, {"kind": "wish", "text": "Évoluer vers le niveau 2."}, headers=HX)
    assert trigger(done)["toast"]["title"] == "Note ajoutée"


def test_a_note_can_be_undone_by_its_author(client_for, company_a):
    client = client_for(company_a.manager)
    done = client.post(
        f"/carriere/fiche/{company_a.employee.public_id}/note/",
        {"kind": "follow_up", "text": "Point de suivi du mois.", "is_private": "on"},
        headers=HX,
    )
    client.post(trigger(done)["toast"]["undo_url"], headers=HX)
    with tenant_context(company_a.company):
        assert not FollowUpNote.objects.filter(text="Point de suivi du mois.").exists()


# ---------- Blocs répétables ----------


def test_adding_a_block_returns_one_empty_row_and_the_new_total(client_for, company_a):
    response = client_for(company_a.manager).post(
        "/blocs/careers-objectives/ajouter/", {"objectives-TOTAL_FORMS": "2"}, headers=HX
    )
    content = response.content.decode()
    assert 'name="objectives-2-title"' in content
    assert re.search(r'name="objectives-TOTAL_FORMS"\s+value="3"[^>]*hx-swap-oob', content)
    assert "objectives-0-title" not in content and "objectives-1-title" not in content


def test_adding_a_block_refuses_an_unknown_form_or_a_bad_index(client_for, company_a):
    client = client_for(company_a.manager)
    assert client.post("/blocs/inconnu/ajouter/", {}).status_code == 404
    bad = client.post("/blocs/careers-objectives/ajouter/", {"objectives-TOTAL_FORMS": "x"})
    assert bad.status_code == 400


# ---------- Exports PDF ----------


def capture_pdf(monkeypatch) -> dict:
    captured = {}

    def fake(template, context, **kwargs):
        captured.update(template=template, context=context)
        return b"%PDF-1.4 test"

    monkeypatch.setattr("apps.core.pdf.render_pdf", fake)
    return captured


def test_review_pdf_is_logged_without_any_name(client_for, company_a, monkeypatch):
    captured = capture_pdf(monkeypatch)
    response = client_for(company_a.employee).get(url(review_of(company_a), "pdf"))
    assert response["Content-Type"] == "application/pdf"
    assert response["Content-Disposition"].startswith('attachment; filename="entretien-')
    assert captured["template"] == "careers/pdf_review.html"
    log = AuditLog.all_companies.get(action="careers.review_exported")
    assert company_a.employee.last_name not in log.summary


def test_the_file_pdf_never_contains_a_private_note(client_for, company_a, monkeypatch):
    captured = capture_pdf(monkeypatch)
    client_for(company_a.manager).get(f"/carriere/fiche/{company_a.employee.public_id}/pdf/")
    with tenant_context(company_a.company):
        notes = list(captured["context"]["notes"])
    assert company_a.requests["note"] in notes
    assert company_a.requests["private_note"] not in notes


def test_pdf_exports_share_the_export_limit(client_for, company_a, monkeypatch):
    capture_pdf(monkeypatch)
    client = client_for(company_a.employee)
    for _ in range(10):
        assert client.get(url(review_of(company_a), "pdf")).status_code == 200
    assert client.get(url(review_of(company_a), "pdf")).status_code == 429
