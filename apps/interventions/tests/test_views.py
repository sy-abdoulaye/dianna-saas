"""Écrans du suivi d'intervention : critères d'acceptation de docs/modules/11-interventions.md,
enregistrement automatique avec version, annulation immédiate et export PDF."""

import json
from html import unescape

import pytest

from apps.core.models import AuditLog
from apps.core.tenancy import tenant_context
from apps.interventions.models import InterventionReport, ReportStatus
from tests.factories import EmployeeFactory

pytestmark = pytest.mark.django_db
HX = {"HX-Request": "true"}
PERIOD = "2026-09"


def text(response) -> str:
    return unescape(response.content.decode())


def trigger(response) -> dict:
    return json.loads(response["HX-Trigger"])


def post_data(**changes) -> dict:
    data = {
        "report": "",
        "version": "",
        "mission": "Refonte de l'espace client",
        "period": PERIOD,
        "visibility": "uncertain",
        "planned_end": "2026-11-30",
        "extension": "non",
        "extension_until": "",
        "follow_up": "",
        "done-TOTAL_FORMS": "2",
        "done-INITIAL_FORMS": "0",
        "done-0-description": "Module de paiement",
        "done-0-completion": "60",
        "done-1-description": "Plan de tests",
        "done-1-completion": "100",
        "next-TOTAL_FORMS": "1",
        "next-INITIAL_FORMS": "0",
        "next-0-description": "Tests de bout en bout",
        "next-0-completion": "0",
    }
    data.update(changes)
    return data


def save(client, act, **changes):
    return client.post(
        "/interventions/enregistrer/", {**post_data(**changes), "act": act}, headers=HX
    )


def report_of(company, person) -> InterventionReport:
    with tenant_context(company):
        return InterventionReport.objects.filter(employee=person).latest("pk")


# ---------- Critères d'acceptation ----------


def test_sending_with_150_percent_shows_between_0_and_100_under_the_field(client_for, company_a):
    response = save(client_for(company_a.employee), "send", **{"done-0-completion": "150"})
    assert response.status_code == 422
    content = text(response)
    assert "Entre 0 et 100." in content
    assert 'id="id_done-0-completion-error"' in content
    assert "Module de paiement" in content and "Plan de tests" in content  # rien n'est perdu


def test_a_draft_needs_only_the_intervention_and_the_period(client_for, company_a):
    client = client_for(company_a.employee)
    done = save(client, "draft", visibility="", planned_end="", **{"done-0-completion": ""})
    assert done.status_code == 204
    assert trigger(done)["toast"]["title"] == "Brouillon enregistré"
    missing = save(client, "draft", mission="", period="")
    content = text(missing)
    assert "Indiquez l'intervention concernée." in content and "Choisissez la période." in content


def test_sending_checks_every_required_field(client_for, company_a):
    response = save(
        client_for(company_a.employee),
        "send",
        visibility="",
        planned_end="",
        extension="oui",
        **{"done-1-description": ""},
    )
    content = text(response)
    for message in (
        "Choisissez la visibilité de l'intervention.",
        "Indiquez la date de fin prévue.",
        "Indiquez jusqu'à quand.",
        "Décrivez le travail réalisé.",
    ):
        assert message in content


def test_an_extension_must_go_beyond_the_planned_end(client_for, company_a):
    response = save(
        client_for(company_a.employee), "send", extension="oui", extension_until="2026-11-01"
    )
    assert "La prolongation doit aller au-delà de la fin prévue." in text(response)


def test_a_second_report_for_the_same_intervention_and_period_is_refused(client_for, company_a):
    client = client_for(company_a.employee)
    save(client, "draft")
    again = save(client, "draft")
    assert again.status_code == 422
    assert "Un compte rendu existe déjà pour cette intervention et cette période." in (text(again))


def test_a_sent_report_is_locked_until_changes_are_requested(client_for, company_a):
    employee, manager = client_for(company_a.employee), client_for(company_a.manager)
    sent = save(employee, "send")
    assert sent.status_code == 204 and "HX-Location" in sent
    report = report_of(company_a.company, company_a.employee)
    edit_url = f"/interventions/{report.public_id}/modifier/"
    assert "ne peut plus être modifié" in text(employee.get(edit_url))
    manager.post(
        f"/interventions/{report.public_id}/complement/",
        {"note": "Précise le risque de retard."},
        headers=HX,
    )
    page = text(employee.get(edit_url))
    assert "Complément demandé" in page and "Précise le risque de retard." in page


def test_the_manager_validates_from_to_validate_and_the_counter_follows(client_for, company_a):
    save(client_for(company_a.employee), "send")
    manager = client_for(company_a.manager)
    page = text(manager.get("/interventions/?onglet=a-valider"))
    assert "Refonte de l'espace client" in page
    assert manager.get("/").context["nav_groups"]  # menu construit
    counts = {
        item.key: item.count
        for group in manager.get("/interventions/").context["nav_groups"]
        for item in group.items
    }
    assert counts["interventions"] == 2  # le compte rendu du jeu de données et le nouveau
    report = report_of(company_a.company, company_a.employee)
    done = manager.post(f"/interventions/{report.public_id}/valider/", {"note": ""}, headers=HX)
    assert trigger(done)["toast"]["title"] == "Compte rendu validé"
    page = text(manager.get("/interventions/?onglet=a-valider"))
    assert "Refonte de l'espace client" not in page


def test_an_employee_cannot_see_a_colleague_report(client_for, company_a):
    colleague = EmployeeFactory(company=company_a.company, manager=company_a.manager)
    save(client_for(colleague), "draft")
    report = report_of(company_a.company, colleague)
    client = client_for(company_a.employee)
    assert client.get(f"/interventions/{report.public_id}/").status_code == 404
    assert client.get(f"/interventions/{report.public_id}/modifier/").status_code == 404
    assert client.get(f"/interventions/{report.public_id}/pdf/").status_code == 404


def test_adding_a_block_returns_only_the_new_one(client_for, company_a):
    response = client_for(company_a.employee).post(
        "/blocs/interventions-done/ajouter/", {"done-TOTAL_FORMS": "2"}, headers=HX
    )
    content = text(response)
    assert 'name="done-2-description"' in content and "Travail réalisé 3" in content
    assert "done-0-description" not in content


def test_a_new_report_takes_the_intervention_and_visibility_of_the_last_one(client_for, company_a):
    page = text(client_for(company_a.employee).get("/interventions/nouveau/"))
    assert 'value="Support niveau 2 · contrat Atlas"' in page
    assert '<option value="planned_end" selected>' in page


# ---------- Enregistrement automatique (Q8) ----------


def test_autosave_creates_the_draft_then_saves_with_the_version(client_for, company_a):
    client = client_for(company_a.employee)
    first = save(client, "autosave")
    assert first.status_code == 200 and "Brouillon enregistré à" in text(first)
    report = report_of(company_a.company, company_a.employee)
    assert first["HX-Replace-Url"] == f"/interventions/{report.public_id}/modifier/"
    assert f'value="{report.public_id}"' in text(first)
    second = save(client, "autosave", report=str(report.public_id), version="1", follow_up="Suite")
    assert second.status_code == 200
    report.refresh_from_db()
    assert report.version == 2 and report.follow_up == "Suite"


def test_autosave_from_another_window_overwrites_nothing(client_for, company_a):
    client = client_for(company_a.employee)
    save(client, "draft")
    report = report_of(company_a.company, company_a.employee)
    save(client, "autosave", report=str(report.public_id), version="1", follow_up="Onglet A")
    stale = save(client, "autosave", report=str(report.public_id), version="1", follow_up="B")
    assert stale.status_code == 409
    assert trigger(stale)["toast"]["title"] == (
        "Ce compte rendu a été modifié dans une autre fenêtre. Rechargez la page."
    )
    manual = save(client, "draft", report=str(report.public_id), version="1", follow_up="B")
    assert "modifié dans une autre fenêtre" in text(manual)
    report.refresh_from_db()
    assert report.follow_up == "Onglet A"


def test_autosave_without_intervention_writes_nothing(client_for, company_a):
    response = save(client_for(company_a.employee), "autosave", mission="")
    assert "Brouillon non enregistré" in text(response)
    with tenant_context(company_a.company):
        assert not InterventionReport.objects.filter(mission__name="").exists()


# ---------- Annulation, remplacement, export ----------


def test_undo_after_sending_returns_to_draft(client_for, company_a):
    client = client_for(company_a.employee)
    sent = save(client, "send")
    client.post(trigger(sent)["toast"]["undo_url"], headers=HX)
    assert report_of(company_a.company, company_a.employee).status == ReportStatus.DRAFT


def test_hr_sees_the_banner_when_acting_for_a_manager(client_for, company_a):
    report = company_a.requests["report"]
    page = text(client_for(company_a.hr).get(f"/interventions/{report.public_id}/"))
    assert f"Vous agissez à la place de {company_a.manager.full_name}." in page


def test_report_pdf_is_logged_without_name(client_for, company_a, monkeypatch):
    monkeypatch.setattr("apps.core.pdf.render_pdf", lambda *a, **k: b"%PDF-1.4")
    report = company_a.requests["report"]
    response = client_for(company_a.manager).get(f"/interventions/{report.public_id}/pdf/")
    assert response["Content-Type"] == "application/pdf"
    log = AuditLog.all_companies.get(action="interventions.exported")
    assert company_a.employee.last_name not in log.summary


def test_sending_from_the_detail_page_asks_for_confirmation(client_for, company_a):
    client = client_for(company_a.employee)
    save(client, "draft")
    report = report_of(company_a.company, company_a.employee)
    confirm = text(client.get(f"/interventions/{report.public_id}/envoyer/"))
    assert "Envoyer le compte rendu ?" in confirm and company_a.manager.full_name in confirm
    sent = client.post(f"/interventions/{report.public_id}/envoyer/", headers=HX)
    assert trigger(sent)["toast"]["title"] == "Compte rendu envoyé"
    again = client.post(f"/interventions/{report.public_id}/envoyer/", headers=HX)
    assert again.status_code == 409
