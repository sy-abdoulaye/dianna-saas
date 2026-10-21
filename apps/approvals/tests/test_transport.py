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
from apps.approvals.models import RequestStatus, TransportProof
from apps.approvals.tests.conftest import next_weekday  # noqa: F401
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

    def broken(*args, **kwargs):
        raise RuntimeError("panne après l'écriture du fichier")

    monkeypatch.setattr(workflow, "_event", broken)
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
        result = workflow.submit(TransportProof, company_a.employee, data)
        storage, name = result.request.file.storage, result.request.file.name
        assert storage.exists(name)
        with django_capture_on_commit_callbacks(execute=True):
            workflow.undo(TransportProof, result.undo_payload("submit"), company_a.employee)
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
        proof = workflow.submit(TransportProof, company_a.hr, data).request
        assert not workflow.can_decide(company_a.hr, proof)
        assert workflow.can_decide(company_a.admin, proof)
        workflow.approve(proof, company_a.admin)
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
    assert response.status_code == 200 and b"".join(response.streaming_content) == PDF_BYTES


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


def test_payroll_export(client_for, company_a):
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
