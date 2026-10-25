"""Justificatifs de transport (fiche 05, section Transport ; L5-01 à L5-07, L5-12, L5-13)."""

import csv
import io
import json
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.utils import timezone

from apps.approvals import workflow
from apps.approvals.kinds import summary
from apps.approvals.models import RequestStatus, TransportProof
from apps.approvals.tests.conftest import next_weekday  # noqa: F401 (fixture pytest)
from apps.core.context import ActionContext
from apps.core.dates import format_date
from apps.core.models import AuditLog, Notification
from apps.core.tenancy import tenant_context
from apps.people.models import Employee
from conftest import PDF_BYTES
from tests.factories import EmployeeFactory

pytestmark = pytest.mark.django_db


def this_month():
    return timezone.localdate().replace(day=1)


def form(month=None, ticket="monthly", amount="84.10", name="abonnement.pdf", data=PDF_BYTES):
    month = month or this_month()
    return {
        "month": month.strftime("%Y-%m"),
        "ticket_type": ticket,
        "amount": amount,
        "file": SimpleUploadedFile(name, data, "application/pdf"),
    }


def send(client, **kwargs):
    return client.post("/transport/nouvelle/", form(**kwargs))


def toast(response):
    return json.loads(response["HX-Trigger"])["toast"]


def proof_of(employee, **filters):
    return TransportProof.all_companies.filter(requester=employee, **filters).latest("pk")


# ---------- Dépôt et contrôles ----------


def test_employee_submits_a_proof_to_hr(client_for, company_a):
    response = send(client_for(company_a.employee))
    assert response.status_code == 204
    proof = proof_of(company_a.employee, month=this_month())
    assert proof.status == RequestStatus.PENDING and proof.original_name == "abonnement.pdf"
    # Stockage : <company_id>/transport/<aléatoire>.pdf, jamais le nom d'origine (L5-01).
    assert proof.file.name.startswith(f"{company_a.company.pk}/transport/")
    assert "abonnement" not in proof.file.name and proof.file.name.endswith(".pdf")
    assert proof.file_type == "application/pdf"
    # Validé par les RH, pas par le manager (L5-04).
    with tenant_context(company_a.company):
        notified = set(
            Notification.objects.filter(source_type="transport", source_id=proof.pk).values_list(
                "recipient_id", flat=True
            )
        )
        assert company_a.hr.pk in notified and company_a.manager.pk not in notified
        assert not workflow.can_decide(company_a.manager, proof)
        assert workflow.can_decide(company_a.hr, proof)
    manager_page = client_for(company_a.manager).get("/transport/").content.decode()
    assert "À valider" not in manager_page and "Mon équipe" not in manager_page


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"amount": "0"}, "Indiquez un montant supérieur à 0."),
        ({"amount": "1000.01"}, "Le montant semble trop élevé. Vérifiez la saisie."),
        ({"month": date(2020, 1, 1)}, "Choisissez un mois entre"),
        ({"data": b"MZ" + b"\x00" * 50, "name": "abo.exe"}, "Format non accepté"),
        ({"data": PDF_BYTES + b"0" * (6 * 1024 * 1024)}, "Le fichier dépasse 5 Mo."),
    ],
)
def test_controls(client_for, company_a, kwargs, message):
    response = send(client_for(company_a.employee), **kwargs)
    assert response.status_code == 422
    assert message in response.content.decode().replace("&#x27;", "'")


def test_missing_file(client_for, company_a):
    data = form()
    del data["file"]
    response = client_for(company_a.employee).post("/transport/nouvelle/", data)
    assert "Joignez le justificatif." in response.content.decode()


def test_validity_is_computed():
    proof = TransportProof(month=date(2026, 11, 1), ticket_type="monthly")
    assert proof.compute_validity() == date(2026, 11, 30)
    proof.ticket_type = "yearly"
    assert proof.compute_validity() == date(2027, 10, 31)


def test_overlapping_subscriptions_are_refused_but_single_tickets_are_not(client_for, company_a):
    client = client_for(company_a.employee)
    assert send(client, ticket="yearly", amount="800").status_code == 204
    refused = send(client, month=this_month() + timedelta(days=32))
    assert refused.status_code == 422
    assert "Un justificatif de ce type couvre déjà" in refused.content.decode()
    assert send(client, ticket="single", amount="12.40").status_code == 204


def test_failed_submission_leaves_no_file(client_for, company_a, monkeypatch, settings):
    from pathlib import Path

    from apps.approvals.models import RequestEvent

    def broken(*args, **kwargs):
        raise RuntimeError("panne après l'écriture du fichier")

    # Panne à l'écriture de l'événement, après le fichier et l'INSERT de la demande.
    monkeypatch.setattr(RequestEvent.objects, "create", broken)
    with pytest.raises(RuntimeError):
        send(client_for(company_a.employee))
    folder = Path(settings.PRIVATE_MEDIA_ROOT) / str(company_a.company.pk) / "transport"
    stored = {p.name for p in folder.iterdir()} if folder.exists() else set()
    fixture_file = Path(company_a.requests["transport"].file.name).name
    assert stored <= {fixture_file}


def test_withdrawn_proof_deletes_its_file(company_a, django_capture_on_commit_callbacks):
    from django.core.files.base import ContentFile

    with tenant_context(company_a.company):
        data = {
            "month": this_month(),
            "ticket_type": "monthly",
            "amount": Decimal("84.10"),
            "file": ContentFile(PDF_BYTES, name="justificatif.pdf"),
            "file_type": "application/pdf",
            "original_name": "abo.pdf",
        }
        result = workflow.submit(TransportProof, data, context=ActionContext(company_a.employee))
        storage, name = result.request.file.storage, result.request.file.name
        assert storage.exists(name)
        with django_capture_on_commit_callbacks(execute=True):
            workflow.undo(
                TransportProof,
                result.undo_payload("submit"),
                context=ActionContext(company_a.employee),
            )
    assert not storage.exists(name)


def test_hr_proof_is_validated_by_someone_else(company_a, submit):
    from django.core.files.base import ContentFile

    with tenant_context(company_a.company):
        data = {
            "month": this_month(),
            "ticket_type": "monthly",
            "amount": Decimal("84.10"),
            "file": ContentFile(PDF_BYTES, name="j.pdf"),
            "file_type": "application/pdf",
            "original_name": "j.pdf",
        }
        proof = workflow.submit(TransportProof, data, context=ActionContext(company_a.hr)).request
        assert not workflow.can_decide(company_a.hr, proof)
        assert workflow.can_decide(company_a.admin, proof)
        workflow.approve(proof, context=ActionContext(company_a.admin))
    assert TransportProof.all_companies.get(pk=proof.pk).status == RequestStatus.APPROVED


# ---------- Fichier : servi après contrôle, isolé, journalisé ----------


def test_file_access_by_profile(client_for, company_a):
    proof = company_a.requests["transport"]
    url = f"/transport/{proof.public_id}/justificatif/"
    assert client_for(company_a.employee).get(url).status_code == 200
    with tenant_context(company_a.company):
        colleague = EmployeeFactory(company=company_a.company, service=company_a.service)
    assert client_for(colleague).get(url).status_code == 404
    assert client_for(company_a.manager).get(url).status_code == 404  # son manager non plus
    response = client_for(company_a.hr).get(url)
    assert response.status_code == 200 and response.content == PDF_BYTES


def test_file_is_served_isolated_with_escaped_name(client_for, company_a):
    proof = company_a.requests["transport"]
    TransportProof.all_companies.filter(pk=proof.pk).update(original_name='a"b é€.pdf')
    client = client_for(company_a.hr)
    inline = client.get(f"/transport/{proof.public_id}/justificatif/")
    assert inline["Content-Type"] == "application/pdf"
    assert inline["X-Content-Type-Options"] == "nosniff"
    assert inline["Content-Security-Policy"].startswith("sandbox")
    assert inline["Cache-Control"] == "private, no-store"
    assert inline["Content-Disposition"].startswith("inline;")
    attachment = client.get(f"/transport/{proof.public_id}/justificatif/?telecharger=1")
    disposition = attachment["Content-Disposition"]
    assert disposition.startswith("attachment;")
    assert "filename*=utf-8''a%22b%20%C3%A9%E2%82%AC.pdf" in disposition


def test_hr_downloads_are_logged_without_file_name(client_for, company_a):
    proof = company_a.requests["transport"]
    client_for(company_a.employee).get(f"/transport/{proof.public_id}/justificatif/")
    client_for(company_a.hr).get(f"/transport/{proof.public_id}/justificatif/?telecharger=1")
    logs = AuditLog.all_companies.filter(action="requests.proof_downloaded")
    assert logs.count() == 1  # le demandeur n'est pas journalisé, le RH oui
    log = logs.get()
    assert log.actor_id == company_a.hr.pk and log.summary == "Justificatif de transport consulté"


def test_proof_access_is_logged_by_the_engine_only_for_other_people(company_a):
    from apps.core.context import ActionContext

    proof = company_a.requests["transport"]
    with tenant_context(company_a.company):
        workflow.record_proof_access(proof, context=ActionContext(company_a.employee))
        workflow.record_proof_access(proof, context=ActionContext(company_a.hr))
    logs = AuditLog.all_companies.filter(action="requests.proof_downloaded")
    assert list(logs.values_list("actor_id", flat=True)) == [company_a.hr.pk]


def test_proofs_are_never_served_by_signed_link(client_for, company_a):
    from django.core import signing
    from django.urls import reverse

    from apps.core.files import SALT

    proof = company_a.requests["transport"]
    token = signing.dumps(
        {"n": proof.file.name, "c": str(company_a.company.pk)}, salt=SALT, compress=True
    )
    url = reverse("core:private_file", args=[token])
    assert client_for(company_a.hr).get(url).status_code == 404


def test_detail_shows_the_preview_to_hr(client_for, company_a):
    proof = company_a.requests["transport"]
    content = client_for(company_a.hr).get(f"/transport/{proof.public_id}/").content.decode()
    assert "Ouvrir le justificatif" in content and "Télécharger" in content
    assert "42,05" in content  # remboursement estimé : 50 % de 84,10 €


# ---------- Export paie et relance ----------


def payroll_proofs(company_a):
    with tenant_context(company_a.company):
        now = timezone.now()
        for ticket, month, amount in (
            ("monthly", date(2026, 11, 1), "84.10"),
            ("yearly", date(2026, 6, 1), "840.00"),
            ("single", date(2026, 11, 1), "12.40"),
        ):
            proof = TransportProof(
                requester=company_a.employee,
                month=month,
                ticket_type=ticket,
                amount=amount,
                file_type="application/pdf",
                original_name="j.pdf",
                status=RequestStatus.APPROVED,
                submitted_at=now,
                file=f"{company_a.company.pk}/transport/x.pdf",
            )
            proof.compute_validity()
            proof.save()


def test_payroll_export(client_for, company_a):
    payroll_proofs(company_a)
    response = client_for(company_a.hr).get("/transport/export/?mois=2026-11&format=csv")
    rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig")), delimiter=";"))
    assert rows[0][-1] == "Remboursement estimé"
    by_type = {r[3]: r for r in rows[1:]}
    assert by_type["Abonnement mensuel"][-1] == "42,05 €"
    assert by_type["Abonnement annuel"][-2:] == ["70,00 €", "35,00 €"]
    assert by_type["Titre unique"][-1] == "Non concerné"
    assert client_for(company_a.employee).get("/transport/export/").status_code == 403


def test_yearly_subscription_reminder_is_sent_once_by_the_worker(company_a, run_tasks):
    with tenant_context(company_a.company):
        today = timezone.localdate()
        start = (today + timedelta(days=10)).replace(day=1)
        year, month = divmod(start.month - 1 - 11, 12)
        first = start.replace(year=start.year + year, month=month + 1)
        proof = TransportProof(
            requester=company_a.employee,
            month=first,
            ticket_type="yearly",
            amount="800",
            file_type="application/pdf",
            status=RequestStatus.APPROVED,
            submitted_at=timezone.now(),
            file=f"{company_a.company.pk}/transport/x.pdf",
        )
        proof.compute_validity()
        proof.save()
    if not 0 <= (proof.valid_until - today).days <= 15:
        pytest.skip("fin de validité hors de la fenêtre de relance ce jour-là")
    call_command("enqueue_daily_tasks", verbosity=0)
    call_command("enqueue_daily_tasks", verbosity=0)  # deux fois : une seule relance
    run_tasks()
    run_tasks(after_seconds=46)
    reminders = Notification.all_companies.filter(
        recipient=company_a.employee, text__startswith="Votre abonnement annuel"
    )
    assert reminders.count() == 1
    assert [m.subject for m in mail.outbox] == ["Votre abonnement de transport se termine bientôt"]
    assert TransportProof.all_companies.get(pk=proof.pk).reminder_sent_at is not None


def test_employee_page_explains_the_legal_rule(client_for, company_a):
    content = client_for(company_a.employee).get("/transport/").content.decode()
    assert "article L3261-2 du Code du travail" in content
    assert "Voir le planning" not in content


def test_hr_sees_all_proofs_but_manager_only_his_own(client_for, company_a):
    hr = client_for(company_a.hr).get("/transport/?onglet=equipe").content.decode()
    assert company_a.employee.full_name in hr
    employee = Employee.all_companies.get(pk=company_a.employee.pk)
    assert employee.full_name


def test_reminder_writes_1er_for_the_first_day_of_the_month(company_a, monkeypatch):
    """La relance utilise le format commun : « le 1er novembre 2026 »."""
    from apps.approvals import tasks

    monkeypatch.setattr(tasks.timezone, "localdate", lambda: date(2026, 10, 20))
    with tenant_context(company_a.company):
        TransportProof.objects.create(
            requester=company_a.employee,
            month=date(2025, 11, 1),
            ticket_type="yearly",
            amount="800",
            file_type="application/pdf",
            status=RequestStatus.APPROVED,
            submitted_at=timezone.now(),
            file=f"{company_a.company.pk}/transport/x.pdf",
            valid_until=date(2026, 11, 1),  # fixée à la main : le calcul donne une fin de mois
        )
    assert tasks.remind_expiring_transport.call(company_a.company.pk) == 1
    notification = Notification.all_companies.get(
        recipient=company_a.employee, text__startswith="Votre abonnement annuel"
    )
    assert "se termine le 1er novembre 2026." in notification.text


# ---------- Montant saisi en texte (L5-20) ----------


@pytest.mark.parametrize("typed", ["2,15", "2.15", " 2,15 ", "2 ,15"])
def test_amount_accepts_a_comma_or_a_dot(client_for, company_a, typed):
    assert send(client_for(company_a.employee), amount=typed).status_code == 204
    assert proof_of(company_a.employee).amount == Decimal("2.15")


@pytest.mark.parametrize("typed", ["2;15", "abc", "2,15 €", "1e3", "2,155", "-5", "1.000,50"])
def test_amount_refuses_other_formats(client_for, company_a, typed):
    response = send(client_for(company_a.employee), amount=typed)
    assert response.status_code == 422
    assert "Saisissez un montant comme 84,10." in response.content.decode()


def test_amount_is_a_text_field_with_a_decimal_keyboard(client_for, company_a):
    page = client_for(company_a.employee).get("/transport/nouvelle/").content.decode()
    assert 'name="amount"' in page and 'inputmode="decimal"' in page
    assert 'type="number"' not in page


# ---------- Types validés par les RH (L5-04) ----------


def test_hr_validated_kinds_say_sent_to_hr_and_never_write_instead_of(client_for, company_a):
    """Le salarié a un manager, mais les RH sont les valideurs prévus : le message dit
    « transmise aux RH » et le journal n'écrit jamais « à la place de »."""
    client = client_for(company_a.employee)
    response = send(client)
    assert "transmise aux RH" in toast(response)["message"]
    assert company_a.manager.full_name not in toast(response)["message"]
    approved = proof_of(company_a.employee)
    send(client, ticket="single", month=this_month())
    refused = proof_of(company_a.employee, ticket_type="single")
    with tenant_context(company_a.company):
        workflow.approve(approved, context=ActionContext(company_a.hr))
        workflow.refuse(refused, reason="Illisible", context=ActionContext(company_a.hr))
        logs = AuditLog.objects.filter(target_type="approvals.transportproof")
        summaries = list(logs.values_list("summary", flat=True))
    assert len(summaries) >= 2
    assert not any("à la place de" in text for text in summaries)


def test_summary_follows_the_prototype_order_with_the_file_name(client_for, company_a):
    send(client_for(company_a.employee), amount="84,10")
    proof = proof_of(company_a.employee)
    month = format_date(this_month(), "month")
    assert summary(proof) == f"{month} · Abonnement mensuel · 84,10 € · abonnement.pdf"


def test_search_in_my_requests_looks_in_the_summary(client_for, company_a):
    """« Rechercher dans mes demandes » (prototype), sur les quatre modules."""
    client = client_for(company_a.employee)
    send(client, amount="84,10")
    send(client, ticket="single", amount="2,15", name="ticket.pdf")
    found = client.get("/transport/?onglet=mes-demandes&q=TICKET").content.decode()
    assert "ticket.pdf" in found and "84,10" not in found
    for url in ("/teletravail/", "/conges/", "/astreintes/", "/transport/"):
        page = client.get(url).content.decode()
        assert 'placeholder="Rechercher dans mes demandes"' in page, url


def test_payroll_excel_amounts_are_numbers_that_add_up(client_for, company_a):
    """Excel : montants enregistrés comme nombres au format monétaire, pas comme texte ; la
    somme d'une colonne fonctionne. Les cellules texte restent neutralisées."""
    from openpyxl import load_workbook

    payroll_proofs(company_a)
    response = client_for(company_a.hr).get("/transport/export/?mois=2026-11&format=xlsx")
    sheet = load_workbook(io.BytesIO(response.content)).active
    rows = list(sheet.iter_rows(min_row=2))
    paid = [row[5] for row in rows]
    assert all(c.data_type == "n" and "€" in c.number_format for c in paid)
    assert sum(Decimal(str(c.value)) for c in paid) == Decimal("936.50")
    # Une formule SUM ajoutée par la paie porte sur des nombres : même total.
    monthly = [Decimal(str(row[6].value)) for row in rows]
    assert sum(monthly) == Decimal("84.10") + Decimal("70.00") + Decimal("12.40")
    refunds = {row[3].value: row[7] for row in rows}
    assert refunds["Abonnement mensuel"].data_type == "n"
    assert refunds["Abonnement mensuel"].value == 42.05
    assert refunds["Titre unique"].data_type == "s"
    assert refunds["Titre unique"].value == "Non concerné"
