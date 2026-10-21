"""Justificatifs : type réel, taille, PDF chiffrés, service isolé (L5-01, L5-03)."""

import io

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from apps.approvals.forms import safe_filename
from apps.core.files import DOCUMENT_MAX_BYTES, clean_document
from conftest import PDF_BYTES


def upload(name, data, content_type="application/octet-stream"):
    return SimpleUploadedFile(name, data, content_type)


def jpeg_with_gps() -> bytes:
    image = Image.new("RGB", (40, 30), (200, 10, 10))
    exif = Image.Exif()
    exif[0x8825] = {2: (48.0, 51.0, 24.0)}  # GPSInfo : latitude
    exif[0x010F] = "Fabricant"
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", exif=exif)
    return buffer.getvalue()


def test_a_valid_pdf_is_accepted_as_is():
    content, extension = clean_document(upload("abo.pdf", PDF_BYTES, "application/pdf"))
    assert extension == "pdf" and content.read() == PDF_BYTES


def test_an_encrypted_pdf_is_refused():
    encrypted = PDF_BYTES.replace(b"trailer<<", b"trailer<</Encrypt 9 0 R")
    with pytest.raises(ValidationError) as error:
        clean_document(upload("abo.pdf", encrypted))
    assert error.value.messages == [
        "Ce PDF est protégé par un mot de passe. Enregistrez-le de nouveau sans protection."
    ]


def test_a_pdf_with_javascript_is_accepted(settings):
    """L5-03 : pas de refus des PDF actifs ; la protection repose sur le service isolé."""
    active = PDF_BYTES.replace(b"/Type/Catalog", b"/Type/Catalog/OpenAction<</S/JavaScript>>")
    _content, extension = clean_document(upload("abo.pdf", active))
    assert extension == "pdf"


@pytest.mark.parametrize(
    ("name", "data", "content_type"),
    [
        ("virus.exe", b"MZ\x90\x00" + b"\x00" * 100, "application/x-msdownload"),
        ("page.pdf", b"<html><script>alert(1)</script></html>", "application/pdf"),
        ("image.png", b"<svg xmlns='http://www.w3.org/2000/svg'></svg>", "image/png"),
        ("tronque.pdf", b"%PDF-1.4\n1 0 obj", "application/pdf"),
        ("vide.pdf", b"", "application/pdf"),
    ],
)
def test_other_types_are_refused_whatever_their_name(name, data, content_type):
    with pytest.raises(ValidationError) as error:
        clean_document(upload(name, data, content_type))
    assert error.value.messages == ["Format non accepté : choisissez un fichier PDF, JPG ou PNG."]


def test_six_megabytes_are_refused():
    big = PDF_BYTES + b"0" * (6 * 1024 * 1024)
    with pytest.raises(ValidationError) as error:
        clean_document(upload("gros.pdf", big))
    assert error.value.messages == ["Le fichier dépasse 5 Mo."]


def test_size_is_checked_while_reading_not_only_on_the_announced_size():
    big = upload("gros.pdf", PDF_BYTES + b"0" * DOCUMENT_MAX_BYTES)
    big.size = 10  # taille annoncée mensongère
    with pytest.raises(ValidationError):
        clean_document(big)


def test_images_are_reencoded_without_metadata():
    content, extension = clean_document(upload("photo.jpg", jpeg_with_gps(), "image/jpeg"))
    assert extension == "jpg"
    image = Image.open(io.BytesIO(content.read()))
    assert image.format == "JPEG" and not image.getexif()


def test_png_is_accepted():
    buffer = io.BytesIO()
    Image.new("RGB", (10, 10)).save(buffer, format="PNG")
    _content, extension = clean_document(upload("scan.png", buffer.getvalue(), "image/png"))
    assert extension == "png"


@pytest.mark.parametrize(
    ("original", "expected"),
    [
        ("abonnement.pdf", "abonnement.pdf"),
        ("C:\\Users\\moi\\abo.PDF", "abo.pdf"),
        ("../../etc/passwd", "passwd.pdf"),
        ('a"b\r\nc.pdf', 'a"bc.pdf'),
        ("", "justificatif.pdf"),
    ],
)
def test_original_names_are_cleaned(original, expected):
    assert safe_filename(original, "pdf") == expected
