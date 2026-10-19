"""Contrôle et réencodage des images (photos, logos) : apps.core.files.clean_image."""

import io
import time

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image, PngImagePlugin

from apps.core import files

SECRETS = (b"exif-secret", b"jpeg-comment-secret", b"png-text-secret", b"xmp-secret")


def bomb_png(width=13_000, height=13_000) -> bytes:
    """Image de 169 millions de pixels qui pèse quelques dizaines de kilo-octets."""
    buffer = io.BytesIO()
    Image.new("1", (width, height)).save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def upload(content: bytes, name="image.png") -> SimpleUploadedFile:
    return SimpleUploadedFile(name, content)


def test_decompression_bomb_is_refused_before_decoding():
    content = bomb_png()
    assert len(content) < 1024 * 1024  # passe la limite de taille du fichier
    started = time.monotonic()
    with pytest.raises(ValidationError) as error:
        files.clean_image(upload(content), max_bytes=2 * 1024 * 1024)
    assert error.value.messages == ["Image trop grande."]
    assert time.monotonic() - started < 2  # refus sur l'en-tête, sans décodage


def test_pillow_bomb_warning_is_an_error_too(monkeypatch):
    # Sans la limite du projet, l'avertissement de Pillow (au-delà de 89 Mpx) devient une erreur.
    monkeypatch.setattr(files, "MAX_IMAGE_PIXELS", 10**12)
    with pytest.raises(ValidationError) as error:
        files.clean_image(upload(bomb_png()), max_bytes=2 * 1024 * 1024)
    assert error.value.messages == ["Image trop grande."]


def test_image_at_the_limit_is_accepted():
    buffer = io.BytesIO()
    Image.new("RGB", (8000, 5000)).save(buffer, format="JPEG")
    cleaned = files.clean_image(upload(buffer.getvalue(), "max.jpg"), max_bytes=10 * 1024**2)
    assert Image.open(cleaned).size == (1024, 640)


def jpeg_with_metadata() -> bytes:
    image = Image.new("RGB", (40, 30), (200, 10, 10))
    exif = image.getexif()
    exif[0x010E] = "exif-secret"  # ImageDescription
    exif[0x0112] = 6  # orientation : rotation de 90°
    buffer = io.BytesIO()
    image.save(
        buffer,
        format="JPEG",
        exif=exif,
        comment=b"jpeg-comment-secret",
        icc_profile=b"icc-profile-bytes" * 4,
        xmp=b"<x:xmpmeta>xmp-secret</x:xmpmeta>",
    )
    return buffer.getvalue()


def png_with_metadata() -> bytes:
    image = Image.new("RGBA", (40, 30), (10, 200, 10, 255))
    info = PngImagePlugin.PngInfo()
    info.add_text("Comment", "png-text-secret")
    info.add_itxt("XML:com.adobe.xmp", "xmp-secret")
    exif = image.getexif()
    exif[0x010E] = "exif-secret"
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", pnginfo=info, exif=exif, icc_profile=b"icc" * 10)
    return buffer.getvalue()


@pytest.mark.parametrize(
    ("content", "name"), [(jpeg_with_metadata(), "a.jpg"), (png_with_metadata(), "a.png")]
)
def test_reencoding_removes_every_metadata(content, name):
    assert b"exif-secret" in content  # l'original porte bien des métadonnées
    cleaned = files.clean_image(upload(content, name), max_bytes=1024 * 1024).read()
    for secret in SECRETS:
        assert secret not in cleaned
    reopened = Image.open(io.BytesIO(cleaned))
    leftovers = {"exif", "comment", "icc_profile", "xmp", "XML:com.adobe.xmp", "Comment"}
    assert not leftovers & set(reopened.info)
    assert not reopened.getexif()


def test_jpeg_orientation_is_applied_before_the_exif_is_dropped():
    cleaned = files.clean_image(upload(jpeg_with_metadata(), "a.jpg"), max_bytes=1024 * 1024)
    assert Image.open(cleaned).size == (30, 40)  # 40 × 30 tourné d'un quart de tour


@pytest.mark.parametrize(
    "content", [b"MZ\x90\x00", b"GIF89a" + b"\x00" * 20, b"\x89PNG\r\n\x1a\n" + b"\x00" * 30]
)
def test_other_files_are_refused(content):
    with pytest.raises(ValidationError) as error:
        files.clean_image(upload(content), max_bytes=1024 * 1024)
    assert error.value.messages == ["Choisissez une image JPG ou PNG."]
