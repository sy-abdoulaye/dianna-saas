"""Fichiers privés (règle 5 de CLAUDE.md) : photos, logos, justificatifs de transport.

- Stockage hors des fichiers statiques, jamais servi directement par le serveur web.
- Noms aléatoires, rangés par entreprise : <company_id>/<dossier>/<uuid>.<ext>.
- Accès par URL signée de courte durée (PRIVATE_FILE_URL_SECONDS, 5 minutes), générée par
  une vue qui a déjà vérifié la permission. Le jeton porte l'entreprise : présenté sur l'hôte
  d'une autre entreprise, il est refusé.
- Images : taille du fichier et dimensions vérifiées avant tout décodage (MAX_IMAGE_PIXELS,
  protection contre les bombes de décompression), type réel vérifié par Pillow (JPG ou PNG),
  puis image reconstruite à partir de ses seuls pixels et réencodée : aucune métadonnée n'est
  conservée (EXIF dont la position GPS, commentaire JPEG, XMP, profil ICC, textes PNG).
- Justificatifs (lot 5, L5-01) : jamais par lien signé. Chaque téléchargement passe par une
  vue qui vérifie la session et la permission, puis `serve_isolated` renvoie le fichier avec
  son type exact, `nosniff` et une politique de sécurité `sandbox` : rien n'est exécuté ni
  affiché comme une page. Le nom d'origine n'est jamais utilisé pour le stockage.

Stockage (T-12, L5-02) : `PRIVATE_STORAGE_BACKEND` = « filesystem » (développement, tests) ou
« s3 » (Scaleway Object Storage fr-par en production, MinIO dans l'intégration continue) :
bucket privé par environnement, chiffrement côté serveur, identifiants en variables
d'environnement.
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
        if settings.PRIVATE_STORAGE_BACKEND == "s3":
            from storages.backends.s3 import S3Storage

            options = {
                "bucket_name": settings.S3_BUCKET,
                "endpoint_url": settings.S3_ENDPOINT_URL,
                "region_name": settings.S3_REGION,
                "access_key": settings.S3_ACCESS_KEY,
                "secret_key": settings.S3_SECRET_KEY,
                "default_acl": "private",
                "querystring_auth": True,  # jamais d'URL publique ; et aucune URL n'est donnée
                "file_overwrite": False,
                "object_parameters": {},
            }
            if settings.S3_SERVER_SIDE_ENCRYPTION:
                options["object_parameters"]["ServerSideEncryption"] = (
                    settings.S3_SERVER_SIDE_ENCRYPTION
                )
            self._wrapped = S3Storage(**options)
        else:
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


# ---------- Justificatifs (lot 5) ----------

DOCUMENT_MAX_BYTES = 5 * 1024 * 1024
DOCUMENT_TYPES = {"pdf": "application/pdf", "jpg": "image/jpeg", "png": "image/png"}
TOO_BIG = gettext_lazy("Le fichier dépasse 5 Mo.")
NOT_A_DOCUMENT = gettext_lazy("Format non accepté : choisissez un fichier PDF, JPG ou PNG.")
ENCRYPTED_PDF = gettext_lazy(
    "Ce PDF est protégé par un mot de passe. Enregistrez-le de nouveau sans protection."
)


def _read_limited(uploaded, max_bytes: int) -> bytes:
    """Lit le fichier par morceaux et s'arrête dès que la limite est dépassée."""
    uploaded.seek(0)
    data = bytearray()
    for chunk in uploaded.chunks(64 * 1024):
        data += chunk
        if len(data) > max_bytes:
            raise ValidationError(TOO_BIG)
    return bytes(data)


def _check_pdf(data: bytes) -> None:
    """PDF : signature, fin de fichier et absence de chiffrement (L5-03). Les autres PDF
    valides sont acceptés : la protection repose sur le service isolé du fichier."""
    if not data.startswith(b"%PDF-") or b"%%EOF" not in data[-2048:]:
        raise ValidationError(NOT_A_DOCUMENT)
    if b"/Encrypt" in data:
        raise ValidationError(ENCRYPTED_PDF)


def clean_document(uploaded, *, max_bytes: int = DOCUMENT_MAX_BYTES) -> tuple[ContentFile, str]:
    """Justificatif PDF, JPG ou PNG : type réel vérifié sur le contenu (jamais sur l'extension
    ni sur le type annoncé par le navigateur), 5 Mo au plus. Une image est réencodée sans
    métadonnées (clean_image). Renvoie (contenu, extension)."""
    if uploaded is None:
        raise ValidationError(NOT_A_DOCUMENT)
    if getattr(uploaded, "size", 0) and uploaded.size > max_bytes:
        raise ValidationError(TOO_BIG)
    data = _read_limited(uploaded, max_bytes)
    if data.startswith(b"%PDF-"):
        _check_pdf(data)
        return ContentFile(data, name="document.pdf"), "pdf"
    try:
        image = clean_image(ContentFile(data), max_bytes=max_bytes, max_side=2400)
    except ValidationError as exc:
        raise ValidationError(NOT_A_DOCUMENT) from exc
    extension = image.name.rsplit(".", 1)[-1]
    return image, extension


def serve_isolated(field_file, *, content_type: str, filename: str, inline: bool):
    """Réponse de téléchargement isolée : type exact, `nosniff`, politique `sandbox` (aucun
    script, aucune page), pas de cache partagé ; nom d'origine échappé (RFC 6266)."""
    from django.http import FileResponse
    from django.utils.http import content_disposition_header

    field_file.open("rb")
    response = FileResponse(field_file, content_type=content_type)
    response["Content-Disposition"] = content_disposition_header(not inline, filename)
    response["X-Content-Type-Options"] = "nosniff"
    response["Content-Security-Policy"] = "sandbox; default-src 'none'; img-src 'self'"
    response["Cache-Control"] = "private, no-store"
    response["Cross-Origin-Resource-Policy"] = "same-origin"
    return response
