"""Stockage S3 réel (T-12, L5-02) : MinIO dans l'intégration continue, Scaleway en production.

Lancé seulement si `S3_TEST_ENDPOINT` est défini (intégration continue). Vérifie : écriture
sous <company_id>/transport/, chiffrement côté serveur, objet privé (aucun accès anonyme), et
lecture par la vue qui contrôle la permission."""

import os
import urllib.error
import urllib.request

import pytest
from django.utils import timezone

from conftest import PDF_BYTES

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.skipif(not os.environ.get("S3_TEST_ENDPOINT"), reason="S3_TEST_ENDPOINT absent"),
]


@pytest.fixture
def s3(settings):
    import boto3
    from django.utils.functional import empty

    from apps.core.files import private_storage

    settings.PRIVATE_STORAGE_BACKEND = "s3"
    settings.S3_ENDPOINT_URL = os.environ["S3_TEST_ENDPOINT"]
    settings.S3_BUCKET = os.environ.get("S3_TEST_BUCKET", "dianna-ci")
    settings.S3_ACCESS_KEY = os.environ["S3_TEST_ACCESS_KEY"]
    settings.S3_SECRET_KEY = os.environ["S3_TEST_SECRET_KEY"]
    settings.S3_REGION = "us-east-1"
    settings.S3_SERVER_SIDE_ENCRYPTION = "AES256"
    private_storage._wrapped = empty
    client = boto3.client(
        "s3",
        endpoint_url=settings.S3_ENDPOINT_URL,
        aws_access_key_id=settings.S3_ACCESS_KEY,
        aws_secret_access_key=settings.S3_SECRET_KEY,
        region_name=settings.S3_REGION,
    )
    existing = {b["Name"] for b in client.list_buckets().get("Buckets", [])}
    if settings.S3_BUCKET not in existing:
        client.create_bucket(Bucket=settings.S3_BUCKET)
    yield client, settings.S3_BUCKET
    private_storage._wrapped = empty


def test_proofs_are_private_encrypted_and_served_after_permission_check(s3, client_for, company_a):
    from django.core.files.uploadedfile import SimpleUploadedFile

    from apps.approvals.models import TransportProof

    client, bucket = s3
    response = client_for(company_a.employee).post(
        "/transport/nouvelle/",
        {
            "month": timezone.localdate().strftime("%Y-%m"),
            "ticket_type": "single",
            "amount": "12.40",
            "file": SimpleUploadedFile("ticket.pdf", PDF_BYTES, "application/pdf"),
        },
    )
    assert response.status_code == 204
    proof = TransportProof.all_companies.filter(original_name="ticket.pdf").get()
    key = proof.file.name
    assert key.startswith(f"{company_a.company.pk}/transport/")
    head = client.head_object(Bucket=bucket, Key=key)
    assert head["ServerSideEncryption"] == "AES256"
    # Aucun accès anonyme à l'objet.
    with pytest.raises(urllib.error.HTTPError) as anonymous:
        urllib.request.urlopen(f"{os.environ['S3_TEST_ENDPOINT']}/{bucket}/{key}")  # noqa: S310
    assert anonymous.value.code == 403
    served = client_for(company_a.hr).get(f"/transport/{proof.public_id}/justificatif/")
    assert b"".join(served.streaming_content) == PDF_BYTES
    assert (
        client_for(company_a.manager).get(f"/transport/{proof.public_id}/justificatif/").status_code
        == 404
    )
