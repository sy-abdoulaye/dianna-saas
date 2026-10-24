"""Corrections de l'audit du lot 5 : stockage indisponible (L5-17), fichiers orphelins (L5-18),
PDF chiffrés à noms échappés (L5-03), contrôles et contraintes dans le service (L5-19),
numéros de série normalisés (L5-09), image MinIO épinglée."""

import time
from decimal import Decimal
from pathlib import Path

import pytest
from botocore.exceptions import EndpointConnectionError
from django.conf import settings as django_settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from django.utils.functional import empty

from apps.approvals import workflow
from apps.approvals.models import TransportProof
from apps.core import files
from apps.core.context import ActionContext
from apps.core.tenancy import tenant_context
from apps.equipment import services as equipment
from apps.equipment.models import EquipmentItem
from apps.people.models import Employee
from conftest import PDF_BYTES

pytestmark = pytest.mark.django_db
UNAVAILABLE = (
    "Le stockage des fichiers est momentanément indisponible. Réessayez dans quelques minutes."
)


def stored_files(company) -> set:
    folder = Path(django_settings.PRIVATE_MEDIA_ROOT) / str(company.pk)
    return (
        {p.relative_to(folder) for p in folder.rglob("*") if p.is_file()}
        if folder.exists()
        else set()
    )


def proof_data(**changes):
    data = {
        "month": timezone.localdate().replace(day=1),
        "ticket_type": "single",
        "amount": Decimal("12.40"),
        "file": ContentFile(PDF_BYTES, name="justificatif.pdf"),
        "file_type": "application/pdf",
        "original_name": "ticket.pdf",
    }
    data.update(changes)
    return data


def broken_storage(monkeypatch):
    def fail(*args, **kwargs):
        raise EndpointConnectionError(endpoint_url="https://s3.fr-par.scw.cloud")

    for method in ("save", "open", "exists", "delete"):
        monkeypatch.setattr(files.private_storage, method, fail)


# ---------- a. Stockage indisponible ----------


def test_s3_client_has_explicit_timeouts_and_retries(settings):
    settings.PRIVATE_STORAGE_BACKEND = "s3"
    settings.S3_BUCKET, settings.S3_ENDPOINT_URL = "b", "https://s3.fr-par.scw.cloud"
    settings.S3_ACCESS_KEY, settings.S3_SECRET_KEY = "k", "s"
    files.private_storage._wrapped = empty
    config = files.private_storage.connection.meta.client.meta.config
    assert (config.connect_timeout, config.read_timeout) == (3, 10)
    assert config.retries["total_max_attempts"] == 2 and config.retries["mode"] == "standard"
    assert (files.S3_CONNECT_TIMEOUT, files.S3_READ_TIMEOUT, files.S3_MAX_ATTEMPTS) == (3, 10, 2)


def test_upload_with_storage_down_answers_503_and_saves_nothing(client_for, company_a, monkeypatch):
    before = TransportProof.all_companies.count()
    broken_storage(monkeypatch)
    response = client_for(company_a.employee).post(
        "/transport/nouvelle/",
        {
            "month": timezone.localdate().strftime("%Y-%m"),
            "ticket_type": "single",
            "amount": "12.40",
            "file": SimpleUploadedFile("t.pdf", PDF_BYTES, "application/pdf"),
        },
    )
    assert response.status_code == 503
    assert UNAVAILABLE in response["HX-Trigger"].encode().decode("unicode_escape")
    assert TransportProof.all_companies.count() == before


def test_download_with_storage_down_answers_a_503_page(client_for, company_a, monkeypatch):
    proof = company_a.requests["transport"]
    broken_storage(monkeypatch)
    response = client_for(company_a.hr).get(f"/transport/{proof.public_id}/justificatif/")
    assert response.status_code == 503
    assert UNAVAILABLE.replace("'", "&#x27;") in response.content.decode() or (
        UNAVAILABLE in response.content.decode()
    )


def test_photos_never_call_exists_and_fail_quietly(client_for, company_a, monkeypatch):
    from apps.core.files import signed_url

    Employee.all_companies.filter(pk=company_a.employee.pk).update(
        photo=f"{company_a.company.pk}/photos/absente.jpg"
    )
    employee = Employee.all_companies.get(pk=company_a.employee.pk)

    def no_exists(*args, **kwargs):
        raise AssertionError("exists() ne doit plus être appelé")

    monkeypatch.setattr(files.private_storage, "exists", no_exists)
    client = client_for(company_a.hr)
    assert client.get(signed_url(employee.photo)).status_code == 404  # fichier absent
    broken_storage(monkeypatch)
    assert client.get(signed_url(employee.photo)).status_code == 404  # stockage en panne
    page = client.get("/annuaire/").content.decode()
    assert "data-fallback" in page  # l'image se retire, les initiales restent


def test_directory_answers_quickly_when_the_storage_does_not_answer(
    client_for, company_a, settings
):
    """Stockage injoignable (adresse non routable) : délai de connexion de 3 s, 2 essais."""
    from apps.core.files import signed_url

    settings.PRIVATE_STORAGE_BACKEND = "s3"
    settings.S3_BUCKET, settings.S3_ENDPOINT_URL = "dianna", "http://10.255.255.1:9000"
    settings.S3_ACCESS_KEY, settings.S3_SECRET_KEY = "k", "s"
    files.private_storage._wrapped = empty
    Employee.all_companies.filter(pk=company_a.employee.pk).update(
        photo=f"{company_a.company.pk}/photos/photo.jpg"
    )
    employee = Employee.all_companies.get(pk=company_a.employee.pk)
    client = client_for(company_a.hr)
    start = time.perf_counter()
    page = client.get("/annuaire/")
    photo = client.get(signed_url(employee.photo))
    elapsed = time.perf_counter() - start
    assert page.status_code == 200 and photo.status_code == 404
    assert elapsed < 15, f"{elapsed:.1f} s"


# ---------- b. Aucun fichier orphelin ----------


def test_data_error_at_insert_leaves_no_file_and_gives_a_message(company_a):
    before = stored_files(company_a.company)
    with (
        tenant_context(company_a.company),
        pytest.raises(workflow.RequestValidationError) as error,
    ):
        workflow.submit(
            TransportProof, company_a.employee, proof_data(original_name="x" * 300 + ".pdf")
        )
    assert error.value.errors == {None: workflow.INVALID_VALUE}
    assert stored_files(company_a.company) == before


def test_photo_is_removed_when_the_creation_fails(company_a):
    from apps.people import services as people

    before = stored_files(company_a.company)
    photo = ContentFile(b"jpeg", name="photo.jpg")
    with tenant_context(company_a.company), pytest.raises(people.PeopleError):
        people.create_employee(
            {"first_name": "x" * 300, "last_name": "Long", "email": "long@exemple.fr"},
            context=ActionContext(company_a.admin),
            photo=photo,
        )
    assert stored_files(company_a.company) == before


# ---------- c. PDF chiffré, noms échappés ----------


def test_encrypted_pdf_with_escaped_name_is_refused():
    encrypted = PDF_BYTES.replace(b"trailer<<", b"trailer<</Encr#79pt 9 0 R")
    with pytest.raises(ValidationError) as error:
        files.clean_document(SimpleUploadedFile("a.pdf", encrypted))
    assert "protégé par un mot de passe" in error.value.messages[0]


# ---------- d. Contrôles et contraintes dans le service ----------


def test_service_checks_the_month_window_and_the_amount(company_a):
    from datetime import date

    with tenant_context(company_a.company):
        with pytest.raises(workflow.RequestValidationError) as month:
            workflow.submit(TransportProof, company_a.employee, proof_data(month=date(2010, 1, 1)))
        with pytest.raises(workflow.RequestValidationError) as amount:
            workflow.submit(TransportProof, company_a.employee, proof_data(amount=Decimal("5000")))
    assert "Choisissez un mois entre" in str(month.value.errors["month"])
    assert amount.value.errors == {"amount": workflow.AMOUNT_RANGE}


def test_integrity_errors_are_translated_by_constraint_name(company_a, monkeypatch):
    monkeypatch.setattr(workflow, "_check_transport", lambda request: {})
    before = stored_files(company_a.company)
    with (
        tenant_context(company_a.company),
        pytest.raises(workflow.RequestValidationError) as error,
    ):
        workflow.submit(TransportProof, company_a.employee, proof_data(amount=Decimal("5000")))
    assert error.value.errors == {"amount": workflow.AMOUNT_RANGE}  # transport_amount_range
    assert stored_files(company_a.company) == before


# ---------- e. Numéro de série normalisé ----------


def test_serial_numbers_are_normalized_in_the_service(company_a):
    with tenant_context(company_a.company):
        item = equipment.add_item(
            kind="laptop",
            model="X",
            serial_number="ＡＢ-123",
            context=ActionContext(company_a.hr),
        )
        assert item.serial_number == "AB-123"
        for duplicate in ("ab-123", "AB - 123", " a b - 1 2 3 "):
            with pytest.raises(equipment.EquipmentError) as error:
                equipment.add_item(
                    kind="laptop",
                    model="X",
                    serial_number=duplicate,
                    context=ActionContext(company_a.hr),
                )
            assert str(error.value.message) == "Ce numéro de série existe déjà dans le parc."
        assert EquipmentItem.objects.filter(serial_number="AB-123").count() == 1


def test_the_database_refuses_a_second_identical_normalized_serial(company_a):
    from django.db import IntegrityError, transaction

    with tenant_context(company_a.company):
        EquipmentItem.objects.create(kind="laptop", model="X", serial_number="ZZ-1")
        with pytest.raises(IntegrityError), transaction.atomic():
            EquipmentItem.objects.create(kind="laptop", model="Y", serial_number="ZZ-1")


# ---------- f. Image MinIO épinglée ----------


def test_ci_minio_image_is_pinned_by_digest():
    ci = (Path(django_settings.BASE_DIR) / ".github" / "workflows" / "ci.yml").read_text()
    assert "bitnamilegacy/minio@sha256:" in ci


# ---------- f. Coupe-circuit (L5-21) ----------


def test_twelve_avatars_with_s3_down_make_a_single_storage_call(
    client_for, company_a, settings, monkeypatch
):
    """S3 injoignable : la première photo tente le stockage (un appel, au plus S3_MAX_ATTEMPTS
    envois réseau selon la configuration botocore), les onze suivantes échouent aussitôt."""
    from botocore.httpsession import URLLib3Session

    from apps.core.files import signed_url
    from tests.factories import EmployeeFactory

    settings.PRIVATE_STORAGE_BACKEND = "s3"
    settings.S3_BUCKET, settings.S3_ENDPOINT_URL = "dianna", "http://127.0.0.1:1"
    settings.S3_ACCESS_KEY, settings.S3_SECRET_KEY = "k", "s"
    files.private_storage._wrapped = empty
    sends, opens = [], []
    real_send, real_open = URLLib3Session.send, files.private_storage.open

    def counting_send(self, request):
        sends.append(request.url)
        return real_send(self, request)

    def counting_open(*args, **kwargs):
        opens.append(args)
        return real_open(*args, **kwargs)

    monkeypatch.setattr(URLLib3Session, "send", counting_send)
    monkeypatch.setattr(files.private_storage, "open", counting_open)
    with tenant_context(company_a.company):
        people = [
            EmployeeFactory(
                company=company_a.company, photo=f"{company_a.company.pk}/photos/{n}.jpg"
            )
            for n in range(12)
        ]
    client = client_for(company_a.hr)
    start = time.perf_counter()
    statuses = [client.get(signed_url(person.photo)).status_code for person in people]
    elapsed = time.perf_counter() - start
    assert statuses == [404] * 12
    assert len(opens) == 1  # une seule tentative auprès du stockage
    assert 1 <= len(sends) <= files.S3_MAX_ATTEMPTS
    assert elapsed < 15


def test_the_circuit_closes_again_after_30_seconds(monkeypatch):
    clock = {"now": 1000.0}
    monkeypatch.setattr(files.time, "monotonic", lambda: clock["now"])
    files._storage_failed(OSError("injoignable"))
    with pytest.raises(files.StorageUnavailableError):
        files.read_private("x")
    clock["now"] += files.CIRCUIT_BREAKER_SECONDS + 1
    with pytest.raises(files.StorageUnavailableError):  # fichier absent : nouvel essai réel
        files.read_private("absent/x.jpg")
    assert files._circuit["open_until"] <= clock["now"]  # un fichier absent n'ouvre pas
