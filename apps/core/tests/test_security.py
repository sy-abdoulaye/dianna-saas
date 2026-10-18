"""Garde-fous de sécurité du lot 0 : CSP stricte et gabarits compatibles."""

import re
from pathlib import Path

from django.conf import settings
from django.utils.csp import CSP

TEMPLATES_DIR = Path(settings.BASE_DIR) / "templates"


def test_csp_forbids_inline_styles_and_eval():
    policy = settings.SECURE_CSP
    assert policy["style-src"] == [CSP.SELF]
    assert policy["script-src"] == [CSP.SELF, CSP.NONCE]
    flat = str(policy)
    assert "unsafe-inline" not in flat and "unsafe-eval" not in flat
    assert policy["frame-ancestors"] == [CSP.NONE]


def test_templates_have_no_inline_style_or_hx_on():
    offenders = []
    for path in TEMPLATES_DIR.rglob("*.html"):
        text = path.read_text()
        if re.search(r"\sstyle=", text) or "hx-on" in text or re.search(r"\son[a-z]+=", text):
            offenders.append(str(path))
    assert offenders == []


def test_only_the_theme_script_is_inline_and_it_has_a_nonce():
    base = (TEMPLATES_DIR / "base.html").read_text()
    inline_scripts = re.findall(r"<script(?![^>]*\ssrc=)[^>]*>", base)
    assert inline_scripts == ['<script nonce="{{ csp_nonce }}">']


def test_htmx_config_disables_eval_and_history_cache():
    base = (TEMPLATES_DIR / "base.html").read_text()
    assert '"allowEval":false' in base
    assert '"historyCacheSize":0' in base
    assert '"includeIndicatorStyles":false' in base
    assert '"code":"422","swap":true' in base
