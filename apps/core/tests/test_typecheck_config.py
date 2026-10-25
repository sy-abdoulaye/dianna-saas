"""Périmètre bloquant de mypy (`make typecheck`) : toute fonction de service, de sélection
et du moteur des demandes est annotée ; seules les bibliothèques sans types, nommées une à
une, sont importées sans vérification."""

import tomllib
from pathlib import Path

CONFIG = tomllib.loads((Path(__file__).resolve().parents[3] / "pyproject.toml").read_text())
MYPY = CONFIG["tool"]["mypy"]


def test_every_function_of_the_blocking_scope_must_be_annotated():
    assert MYPY["disallow_untyped_defs"] is True
    assert MYPY["disallow_incomplete_defs"] is True
    assert MYPY["check_untyped_defs"] is True
    assert set(MYPY["files"]) == {
        "apps/*/services.py",
        "apps/*/selectors.py",
        "apps/approvals/workflow/*.py",
    }


def test_missing_imports_are_ignored_only_for_named_untyped_libraries():
    assert "ignore_missing_imports" not in MYPY
    overrides = [o for o in MYPY["overrides"] if o.get("ignore_missing_imports")]
    named = {module for override in overrides for module in override["module"]}
    assert named == {"allauth.*", "botocore.*", "environ", "storages.*"}
    assert not any(module.startswith("apps") for module in named)
