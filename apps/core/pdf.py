"""Exports PDF (T-15, WeasyPrint) avec un récupérateur d'URL fermé (L4-06).

WeasyPrint suit les adresses trouvées dans le document (images, feuilles de style, polices).
Le récupérateur ci-dessous n'accepte que :
- les fichiers statiques de Dianna utiles au PDF (polices, feuilles de style), sous
  https://dianna.invalid/static/ ;
- le logo de l'entreprise courante, sous https://dianna.invalid/logo.
Toute autre adresse est refusée sans requête : file://, http(s)://, data:, adresses
internes. Les libellés saisis restent échappés par les gabarits ; même une balise ou un url()
glissé dans le document ne déclencherait aucune requête.
"""

import mimetypes
from pathlib import Path, PurePosixPath

from django.contrib.staticfiles import finders
from django.template.loader import render_to_string
from weasyprint import HTML
from weasyprint.urls import URLFetcher, URLFetcherResponse

ORIGIN = "https://dianna.invalid/"
STATIC_URL = ORIGIN + "static/"
LOGO_URL = ORIGIN + "logo"
STATIC_ALLOWED = {".css": "text/css", ".woff2": "font/woff2"}
PDF_CONTENT_TYPE = "application/pdf"


class URLRefusedError(ValueError):
    pass


class DiannaURLFetcher(URLFetcher):
    def __init__(self, company=None):
        super().__init__(allowed_protocols=(), allow_redirects=False)
        self.company = company
        self.requested = []

    def fetch(self, url, headers=None):
        self.requested.append(url)
        if url.startswith(STATIC_URL):
            return self._static(url, url[len(STATIC_URL) :])
        if url == LOGO_URL:
            return self._logo(url)
        raise URLRefusedError(f"Adresse refusée par le PDF : {url[:80]}")

    def _static(self, url, path):
        clean = PurePosixPath(path.split("?", 1)[0].split("#", 1)[0])
        if clean.is_absolute() or ".." in clean.parts or clean.suffix not in STATIC_ALLOWED:
            raise URLRefusedError(f"Fichier statique refusé : {path[:80]}")
        if clean.parts[0] not in ("css", "fonts"):
            raise URLRefusedError(f"Fichier statique refusé : {path[:80]}")
        found = finders.find(str(clean))
        if not found:
            raise URLRefusedError(f"Fichier statique introuvable : {path[:80]}")
        body = Path(found).read_bytes()
        return URLFetcherResponse(url, body, {"Content-Type": STATIC_ALLOWED[clean.suffix]})

    def _logo(self, url):
        logo = getattr(self.company, "logo", None)
        if not logo:
            raise URLRefusedError("Aucun logo")
        with logo.open("rb") as handle:
            body = handle.read()
        mime = mimetypes.guess_type(logo.name)[0] or "application/octet-stream"
        return URLFetcherResponse(url, body, {"Content-Type": mime})


def render_pdf(template: str, context: dict, *, company=None, fetcher=None) -> bytes:
    return render_document(template, context, company=company, fetcher=fetcher).write_pdf()


def render_document(template: str, context: dict, *, company=None, fetcher=None):
    """Document WeasyPrint mis en page (pages, dimensions) avant l'écriture du PDF."""
    from apps.core.tokens import light_tokens

    html = render_to_string(
        template,
        {
            **context,
            "pdf_static": STATIC_URL,
            "pdf_logo": LOGO_URL if getattr(company, "logo", None) else "",
            "pdf_tokens": {k: v for k, v in light_tokens().items() if v.startswith("#")},
        },
    )
    fetcher = fetcher or DiannaURLFetcher(company)
    return HTML(string=html, base_url=ORIGIN, url_fetcher=fetcher).render()


def pdf_response(request, template: str, context: dict, *, filename: str, back_url: str):
    """Document PDF d'un écran (entretien, fiche de suivi, compte rendu) : même limite de
    fréquence que tous les exports (ratelimit.record_export) et même récupérateur fermé que
    le planning. L'appelant contrôle la permission avant et journalise après."""
    from apps.core.http import attachment
    from apps.core.ratelimit import export_limited_response, record_export

    if not record_export(request.employee):
        return export_limited_response(request, back_url)
    content = render_pdf(template, context, company=request.company)
    return attachment(content, PDF_CONTENT_TYPE, filename)
