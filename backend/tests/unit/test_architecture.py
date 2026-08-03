"""Test de arquitectura: `domain` no puede importar de las capas externas.

CLAUDE.md §3.1: "domain no importa de application, infrastructure ni
presentation". La dirección de las dependencias apunta siempre hacia adentro.
"""

import ast
from pathlib import Path

FORBIDDEN_PREFIXES = ("src.application", "src.infrastructure", "src.presentation")

SRC_ROOT = Path(__file__).resolve().parents[2] / "src"
DOMAIN_ROOT = SRC_ROOT / "domain"


def _imported_modules(tree: ast.Module) -> list[str]:
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    return modules


def _domain_python_files() -> list[Path]:
    if not DOMAIN_ROOT.exists():
        return []
    return sorted(DOMAIN_ROOT.rglob("*.py"))


def test_domain_has_no_outward_dependencies() -> None:
    violations: dict[str, list[str]] = {}

    for path in _domain_python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        forbidden = [
            module
            for module in _imported_modules(tree)
            if module.startswith(FORBIDDEN_PREFIXES)
        ]
        if forbidden:
            violations[str(path.relative_to(SRC_ROOT))] = forbidden

    assert not violations, (
        "`domain` no debe importar de application/infrastructure/presentation "
        f"(CLAUDE.md §3.1). Violaciones encontradas: {violations}"
    )


def test_domain_package_exists() -> None:
    assert DOMAIN_ROOT.is_dir(), "El paquete src/domain/ debe existir."
