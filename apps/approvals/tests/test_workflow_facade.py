"""Façade du moteur des demandes (CLAUDE.md, « Moteur des demandes ») : hors du paquet, un
seul point d'entrée qui n'exporte que des noms publics ; à l'intérieur, des imports directs
entre modules, sans cycle et sans repasser par la façade."""

import ast
import re
from pathlib import Path

from apps.approvals import workflow

ROOT = Path(__file__).resolve().parents[3]
PACKAGE = ROOT / "apps" / "approvals" / "workflow"


def internal_imports() -> dict[str, set[str]]:
    graph = {}
    for path in PACKAGE.glob("*.py"):
        if path.stem == "__init__":
            continue
        deps = set()
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, ast.ImportFrom) or not node.module:
                continue
            if node.module.startswith("apps.approvals.workflow."):
                deps.add(node.module.rsplit(".", 1)[1])
            names = {alias.name for alias in node.names}
            if node.module == "apps.approvals.workflow" or (
                node.module == "apps.approvals" and "workflow" in names
            ):
                deps.add("__init__")
        graph[path.stem] = deps
    return graph


def test_the_facade_exports_only_public_names():
    exported = [name for name in vars(workflow) if not name.startswith("__")]
    assert workflow.__all__ and not [name for name in workflow.__all__ if name.startswith("_")]
    submodules = set(internal_imports())
    assert not [n for n in exported if n.startswith("_") and n not in submodules]


def test_no_code_reaches_a_private_name_through_the_facade():
    """Applications, tests et seed_demo compris."""
    private = re.compile(r"\bworkflow\._[a-z]")
    found = [
        f"{path.relative_to(ROOT)}:{number}"
        for folder in ("apps", "tests", "config")
        for path in (ROOT / folder).rglob("*.py")
        for number, line in enumerate(path.read_text().splitlines(), 1)
        if private.search(line)
    ]
    assert found == []


def test_engine_modules_import_each_other_directly_without_cycle():
    graph = internal_imports()
    assert not [name for name, deps in graph.items() if "__init__" in deps]
    done: set[str] = set()

    def visit(name: str, path: tuple[str, ...]) -> None:
        assert name not in path, f"import circulaire : {' -> '.join((*path, name))}"
        if name in done:
            return
        for dep in graph.get(name, ()):
            visit(dep, (*path, name))
        done.add(name)

    for name in graph:
        visit(name, ())
