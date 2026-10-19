import io

import pytest
from PIL import Image


def image_bytes(fmt="PNG", size=(64, 64)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, (37, 89, 207)).save(buffer, format=fmt)
    return buffer.getvalue()


@pytest.fixture(autouse=True)
def private_media(settings, tmp_path):
    settings.PRIVATE_MEDIA_ROOT = tmp_path / "private"
    from apps.core.files import private_storage

    private_storage._wrapped = None
    private_storage.__dict__.pop("_wrapped", None)
    from django.utils.functional import empty

    private_storage._wrapped = empty
    yield
    private_storage._wrapped = empty
