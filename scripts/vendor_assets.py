"""Copie dans le dépôt les ressources front tierces, à version fixée (L0-07).

    uv run python -I scripts/vendor_assets.py

Chaque paquet npm est téléchargé depuis le registre officiel et vérifié avec l'empreinte
SHA-512 publiée par npm avant extraction. Le script régénère :
- static/vendor/htmx.min.js (+ licence)
- static/fonts/*.woff2 (+ licences OFL)
- static/icons/sprite.svg (+ licence ISC de Lucide)
Les fichiers produits sont versionnés : le script ne sert qu'à mettre à jour une version.
"""

import base64
import hashlib
import io
import re
import sys
import tarfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"

PACKAGES = {
    "htmx": (
        "https://registry.npmjs.org/htmx.org/-/htmx.org-2.0.11.tgz",
        "sha512-Thx/WtpeOQqSrqBCw/A1cwGJGg4UrVa3+sW0GmrM3p4gJgO89ecH4qtbnyzDDWFvBTqjnIMCgELTNt636dtamA==",
    ),
    "plex-sans": (
        "https://registry.npmjs.org/@fontsource-variable/ibm-plex-sans/-/ibm-plex-sans-5.3.0.tgz",
        "sha512-agG8tXFEo0hD9+J7npa4vbbWult52eMLVaQ6WQRlhs/iCAojrMAoejru85W9HTVXHfyUj96KM7gp/KGAS87XaQ==",
    ),
    "plex-mono": (
        "https://registry.npmjs.org/@fontsource/ibm-plex-mono/-/ibm-plex-mono-5.3.0.tgz",
        "sha512-eTgnZjZEGk1QtD3ZstF+Vclo2HLAni8YMy34/DxllwZvyz1lR/1RF/xTiAquOBO7MvqBx8D2Ig2WCPMVfdZu7Q==",
    ),
    "schibsted": (
        "https://registry.npmjs.org/@fontsource-variable/schibsted-grotesk/-/schibsted-grotesk-5.3.0.tgz",
        "sha512-ndS6H/KICWANchlHF3q4UdZD+xrZ3Ji0rUobIuXlgvDUzDfqZDsVuXPXZb636nJZMHE9zZ9Fmwgqazm8hMB50Q==",
    ),
    "lucide": (
        "https://registry.npmjs.org/lucide-static/-/lucide-static-1.50.0.tgz",
        "sha512-Pge6F5Au0bEBvjaeBIjfU5PsmA43FHdM3s5g3rYqSNWvBO3o7WwDSNQSavwX76z/OoSCjwSVbQpGA9lqKud/WA==",
    ),
}

# Clé courte utilisée dans les templates ({% icon "home" %}) → nom de l'icône Lucide.
# Les clés reprennent celles du prototype ; les icônes sont celles de Lucide (design system).
ICONS = {
    "dash": "layout-dashboard",
    "users": "users",
    "cal": "calendar",
    "home": "house",
    "clock": "clock",
    "ticket": "ticket",
    "laptop": "laptop",
    "sun": "sun",
    "moon": "moon",
    "monitor": "monitor",
    "up": "trending-up",
    "clip": "clipboard-list",
    "mega": "megaphone",
    "set": "sliders-horizontal",
    "search": "search",
    "bell": "bell",
    "plus": "plus",
    "check": "check",
    "lock": "lock",
    "edit": "pencil",
    "chev": "chevron-down",
    "left": "chevron-left",
    "right": "chevron-right",
    "mail": "mail",
    "phone": "phone",
    "pin": "map-pin",
    "more": "ellipsis",
    "info": "info",
    "alert": "circle-alert",
    "x": "x",
    "grid": "layout-grid",
    "list": "list",
    "menu": "menu",
    "dl": "download",
    "trash": "trash-2",
    "file": "file-text",
    "out": "log-out",
    "pause": "pause",
    "brief": "briefcase",
    "star": "star",
    "tool": "wrench",
    "chart": "chart-column",
    "send": "send",
    "upload": "upload",
    "copy": "copy",
    "undo": "undo-2",
}


def fetch(name: str) -> tarfile.TarFile:
    url, integrity = PACKAGES[name]
    print(f"- {name} : {url}")
    with urllib.request.urlopen(url, timeout=60) as resp:
        data = resp.read()
    algo, expected = integrity.split("-", 1)
    digest = base64.b64encode(hashlib.new(algo, data).digest()).decode()
    if digest != expected:
        sys.exit(f"Empreinte invalide pour {name} : {digest} != {expected}")
    return tarfile.open(fileobj=io.BytesIO(data), mode="r:gz")


def read(tar: tarfile.TarFile, path: str) -> bytes:
    member = tar.getmember(f"package/{path}")
    return tar.extractfile(member).read()


def write(rel: str, content: bytes) -> None:
    target = STATIC / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)


def vendor_htmx() -> None:
    tar = fetch("htmx")
    write("vendor/htmx.min.js", read(tar, "dist/htmx.min.js"))
    write("vendor/htmx.LICENSE.txt", read(tar, "LICENSE"))


def vendor_fonts() -> None:
    files = {
        "plex-sans": [
            ("files/ibm-plex-sans-latin-wght-normal.woff2", "IBMPlexSans-Variable.woff2"),
        ],
        "plex-mono": [
            ("files/ibm-plex-mono-latin-400-normal.woff2", "IBMPlexMono-Regular.woff2"),
            ("files/ibm-plex-mono-latin-500-normal.woff2", "IBMPlexMono-Medium.woff2"),
        ],
        "schibsted": [
            (
                "files/schibsted-grotesk-latin-wght-normal.woff2",
                "SchibstedGrotesk-Variable.woff2",
            ),
        ],
    }
    for pkg, pairs in files.items():
        tar = fetch(pkg)
        for src, dst in pairs:
            write(f"fonts/{dst}", read(tar, src))
        write(f"fonts/LICENSE-{pkg}.txt", read(tar, "LICENSE"))


def vendor_icons() -> None:
    tar = fetch("lucide")
    symbols = []
    for key, lucide_name in sorted(ICONS.items()):
        svg = read(tar, f"icons/{lucide_name}.svg").decode()
        body = re.search(r"<svg[^>]*>(.*)</svg>", svg, re.S).group(1)
        body = re.sub(r"<!--.*?-->", "", body, flags=re.S)
        body = re.sub(r"\s+", " ", body).strip()
        symbols.append(f'<symbol id="i-{key}" viewBox="0 0 24 24">{body}</symbol>')
    # Symbole de la marque : un D dans une grille 3 × 3 (repris du prototype, symbole #mark).
    mark = (
        '<symbol id="mark" viewBox="0 0 48 48">'
        '<rect width="48" height="48" rx="12" fill="currentColor"/>'
        '<g fill="#FFFFFF"><rect x="8" y="8" width="8" height="8" rx="2"/>'
        '<rect x="8" y="20" width="8" height="8" rx="2"/><rect x="8" y="32" width="8" height="8" rx="2"/>'
        '<rect x="20" y="8" width="8" height="8" rx="2"/><rect x="20" y="32" width="8" height="8" rx="2"/>'
        '<rect x="32" y="20" width="8" height="8" rx="2"/></g>'
        '<g fill="#FFFFFF" fill-opacity=".35"><rect x="20" y="20" width="8" height="8" rx="2"/>'
        '<rect x="32" y="8" width="8" height="8" rx="2"/><rect x="32" y="32" width="8" height="8" rx="2"/></g>'
        "</symbol>"
    )
    sprite = (
        '<svg xmlns="http://www.w3.org/2000/svg">\n'
        "<!-- Icônes Lucide (licence ISC, voir LICENSE-lucide.txt), généré par scripts/vendor_assets.py -->\n"
        + "\n".join(symbols)
        + "\n"
        + mark
        + "\n</svg>\n"
    )
    write("icons/sprite.svg", sprite.encode())
    write("icons/LICENSE-lucide.txt", read(tar, "LICENSE"))


if __name__ == "__main__":
    vendor_htmx()
    vendor_fonts()
    vendor_icons()
    print("Terminé.")
