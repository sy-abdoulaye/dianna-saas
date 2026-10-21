"""Jetons de couleur du design system, lus dans static/css/app.css (thème clair).

Les exports (Excel, PDF) reprennent les couleurs du planning sans les recopier : la seule
source reste app.css (règle 3 de CLAUDE.md)."""

import re
from functools import lru_cache
from pathlib import Path

from django.conf import settings

TOKEN = re.compile(r"--([a-z0-9-]+)\s*:\s*([^;]+);")


@lru_cache(maxsize=1)
def light_tokens() -> dict[str, str]:
    css = (Path(settings.BASE_DIR) / "static" / "css" / "app.css").read_text(encoding="utf-8")
    start = css.index(":root")
    block = css[css.index("{", start) + 1 : css.index("}", start)]
    return {name: value.strip() for name, value in TOKEN.findall(block)}


def color(name: str) -> str:
    """Valeur hexadécimale sans « # » (format openpyxl), ex. color("site-bg") → "DEE9FF"."""
    return light_tokens()[name].lstrip("#").upper()
