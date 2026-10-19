"""Fichiers privés (règle 5 de CLAUDE.md) : photos, logos, puis justificatifs (lot 5).

- Stockage hors des fichiers statiques, jamais servi directement par le serveur web.
- Noms aléatoires, rangés par entreprise : <company_id>/<dossier>/<uuid>.<ext>.
- Accès par URL signée de courte durée (PRIVATE_FILE_URL_SECONDS, 5 minutes), générée par
  une vue qui a déjà vérifié la permission. Le jeton porte l'entreprise : présenté sur l'hôte
  d'une autre entreprise, il est refusé.
- Images : taille du fichier et dimensions vérifiées avant tout décodage (MAX_IMAGE_PIXELS,
  protection contre les bombes de décompression), type réel vérifié par Pillow (JPG ou PNG),
  puis image reconstruite à partir de ses seuls pixels et réencodée : aucune métadonnée n'est
  conservée (EXIF dont la position GPS, commentaire JPEG, XMP, profil ICC, textes PNG).
En production, le stockage objet S3 (T-12) remplacera FileSystemStorage (lot 5).
"""

import io
import uuid
import warnings

from django.conf import settings
from django.core import signing
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.urls import reverse
from django.utils.functional import LazyObject
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

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

# Dimensions maximales acceptées, vérifiées sur l'en-tête avant tout décodage : 40 millions de
# pixels (par exemple 8 000 × 5 000, au-delà de tout appareil photo courant). Une image plus
# grande est refusée : décodée, elle occuperait plus de 160 Mo de mémoire (4 octets par pixel).
MAX_IMAGE_PIXELS = 40_000_000
TOO_LARGE = gettext_lazy("Image trop grande.")
NOT_AN_IMAGE = gettext_lazy("Choisissez une image JPG ou PNG.")
# Modes conservés tels quels ; les autres (palette, 16 bits…) sont convertis.
KEPT_MODES = {"JPEG": ("RGB", "L"), "PNG": ("RGB", "RGBA", "L", "LA")}


def clean_image(uploaded, *, max_bytes: int, max_side: int = 1024) -> ContentFile:
    """Vérifie une image JPG ou PNG et la réencode sans aucune métadonnée, réduite si besoin."""
    from PIL import Image, ImageOps, UnidentifiedImageError

    if uploaded.size > max_bytes:
        raise ValidationError(_("Le fichier dépasse %(n)s Mo.") % {"n": max_bytes // (1024 * 1024)})
    with warnings.catch_warnings():
        # Seconde barrière : l'avertissement de Pillow devient une erreur.
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        try:
            image = Image.open(uploaded)  # lit l'en-tête seulement
            image_format = image.format
            width, height = image.size
            if image_format not in IMAGE_FORMATS:
                raise ValidationError(NOT_AN_IMAGE)
            if width * height > MAX_IMAGE_PIXELS:
                raise ValidationError(TOO_LARGE)
            image.verify()
            uploaded.seek(0)
            image = Image.open(uploaded)
            image.load()
        except (Image.DecompressionBombWarning, Image.DecompressionBombError) as exc:
            raise ValidationError(TOO_LARGE) from exc
        except (UnidentifiedImageError, OSError, ValueError, SyntaxError) as exc:
            raise ValidationError(NOT_AN_IMAGE) from exc
    image = ImageOps.exif_transpose(image)  # applique l'orientation avant de perdre l'EXIF
    if image.mode not in KEPT_MODES[image_format]:
        image = image.convert("RGBA" if image_format == "PNG" else "RGB")
    image.thumbnail((max_side, max_side))
    # Nouvelle image construite à partir des seuls pixels : aucune information (`info`) de
    # l'original ne peut être réécrite par l'encodeur.
    clean = Image.frombytes(image.mode, image.size, image.tobytes())
    buffer = io.BytesIO()
    if image_format == "JPEG":
        clean.save(buffer, format="JPEG", quality=88)
    else:
        clean.save(buffer, format="PNG", optimize=True)
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
