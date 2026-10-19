"""Fichiers privés (règle 5 de CLAUDE.md) : photos, logos, puis justificatifs (lot 5).

- Stockage hors des fichiers statiques, jamais servi directement par le serveur web.
- Noms aléatoires, rangés par entreprise : <company_id>/<dossier>/<uuid>.<ext>.
- Accès par URL signée de courte durée (PRIVATE_FILE_URL_SECONDS, 5 minutes), générée par
  une vue qui a déjà vérifié la permission. Le jeton porte l'entreprise : présenté sur l'hôte
  d'une autre entreprise, il est refusé.
- Images : type et taille vérifiés côté serveur, puis réencodées (les métadonnées EXIF, dont
  la position GPS, sont supprimées).
En production, le stockage objet S3 (T-12) remplacera FileSystemStorage (lot 5).
"""

import io
import uuid

from django.conf import settings
from django.core import signing
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.urls import reverse
from django.utils.functional import LazyObject
from django.utils.translation import gettext as _

SALT = "dianna.private-file"


class PrivateStorage(LazyObject):
    def _setup(self):
        self._wrapped = FileSystemStorage(location=settings.PRIVATE_MEDIA_ROOT, base_url=None)


private_storage = PrivateStorage()


def random_name(prefix: str, filename: str) -> str:
    """Nom aléatoire sous le préfixe de l'entreprise : <company_id>/<dossier>/<uuid>.<ext>."""
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    return f"{prefix}/{uuid.uuid4().hex}.{extension}"


IMAGE_FORMATS = {"JPEG": ("jpg", "image/jpeg"), "PNG": ("png", "image/png")}


def clean_image(uploaded, *, max_bytes: int, max_side: int = 1024) -> ContentFile:
    """Vérifie une image JPG ou PNG et la réencode (sans métadonnées, réduite si besoin)."""
    from PIL import Image, UnidentifiedImageError

    if uploaded.size > max_bytes:
        raise ValidationError(_("Le fichier dépasse %(n)s Mo.") % {"n": max_bytes // (1024 * 1024)})
    try:
        image = Image.open(uploaded)
        image.verify()
        uploaded.seek(0)
        image = Image.open(uploaded)
        image_format = image.format
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ValidationError(_("Choisissez une image JPG ou PNG.")) from exc
    if image_format not in IMAGE_FORMATS:
        raise ValidationError(_("Choisissez une image JPG ou PNG."))
    image.thumbnail((max_side, max_side))
    if image_format == "JPEG" and image.mode not in ("RGB", "L"):
        image = image.convert("RGB")
    buffer = io.BytesIO()
    image.save(buffer, format=image_format)  # pas d'exif= : les métadonnées sont perdues
    extension = IMAGE_FORMATS[image_format][0]
    return ContentFile(buffer.getvalue(), name=f"image.{extension}")


def signed_url(field_file) -> str:
    """URL signée vers un fichier privé, à n'appeler qu'après le contrôle de permission."""
    if not field_file:
        return ""
    company_id = field_file.name.split("/", 1)[0]
    token = signing.dumps({"n": field_file.name, "c": company_id}, salt=SALT, compress=True)
    return reverse("core:private_file", args=[token])


def read_token(token: str) -> dict:
    return signing.loads(token, salt=SALT, max_age=settings.PRIVATE_FILE_URL_SECONDS)
