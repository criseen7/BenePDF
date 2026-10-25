"""Prueba de frontera entre capas (sección 3 del plan)."""

from __future__ import annotations

import ast
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[2] / "src" / "bene"
ADAPTER = PACKAGE / "infrastructure" / "pdf" / "pymupdf_engine.py"


def python_files() -> list[Path]:
    files = sorted(PACKAGE.rglob("*.py"))
    assert files, f"No se encontraron módulos en {PACKAGE}"
    return files


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.add(node.module)
    return modules


def uses_any(path: Path, prefixes: tuple[str, ...]) -> bool:
    return any(
        module == prefix or module.startswith(f"{prefix}.")
        for module in imported_modules(path)
        for prefix in prefixes
    )


def test_pymupdf_solo_se_importa_en_el_adaptador() -> None:
    offenders = [
        path for path in python_files() if uses_any(path, ("pymupdf", "fitz")) and path != ADAPTER
    ]

    assert offenders == []


def test_pyside6_solo_se_importa_en_presentacion_y_entrada() -> None:
    offenders = []
    for path in python_files():
        if not uses_any(path, ("PySide6",)):
            continue
        relative = path.relative_to(PACKAGE)
        allowed = relative == Path("main.py") or relative.parts[0] == "presentation"
        if not allowed:
            offenders.append(relative)

    assert offenders == []


def test_dominio_no_depende_de_capas_exteriores() -> None:
    forbidden = (
        "bene.application",
        "bene.infrastructure",
        "bene.presentation",
        "bene.bootstrap",
        "bene.main",
    )

    for path in (PACKAGE / "domain").rglob("*.py"):
        assert not uses_any(path, forbidden), path
        assert not uses_any(path, ("PySide6", "pymupdf", "fitz")), path


def test_aplicacion_no_depende_de_infraestructura_ni_interfaz() -> None:
    forbidden = ("bene.infrastructure", "bene.presentation", "bene.bootstrap", "bene.main")

    for path in (PACKAGE / "application").rglob("*.py"):
        assert not uses_any(path, forbidden), path
        assert not uses_any(path, ("PySide6", "pymupdf", "fitz")), path


def test_la_presentacion_no_conoce_el_motor_pdf() -> None:
    for path in (PACKAGE / "presentation").rglob("*.py"):
        assert not uses_any(path, ("pymupdf", "fitz")), path
