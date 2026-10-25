"""Pruebas del caso de uso de apertura."""

from __future__ import annotations

from pathlib import Path

import pytest

from bene.application.use_cases.open_document import OpenDocument
from bene.domain.errors import (
    DocumentAccessError,
    DocumentNotFoundError,
    DocumentTooLargeError,
    UnsupportedDocumentError,
)
from tests.unit.fakes import FakePdfEngine, make_pages


def write_file(path: Path, content: bytes = b"%PDF-1.4\n") -> Path:
    path.write_bytes(content)
    return path


def test_abre_y_devuelve_la_sesion(tmp_path: Path) -> None:
    path = write_file(tmp_path / "documento.pdf")
    engine = FakePdfEngine(make_pages(3))

    document = OpenDocument(engine)(path)

    assert document.info.page_count == 3
    assert engine.opened == [(path, None)]


def test_acepta_str_y_expande_el_usuario(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = write_file(tmp_path / "documento.pdf")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    engine = FakePdfEngine(make_pages(1))

    document = OpenDocument(engine)(f"~/{path.name}")

    assert document.info.page_count == 1


def test_delega_la_contrasena_al_motor(tmp_path: Path) -> None:
    path = write_file(tmp_path / "cifrado.pdf")
    engine = FakePdfEngine(make_pages(1))

    OpenDocument(engine)(path, password="clave")

    assert engine.opened == [(path, "clave")]


def test_ruta_inexistente(tmp_path: Path) -> None:
    engine = FakePdfEngine(make_pages(1))

    with pytest.raises(DocumentNotFoundError) as excinfo:
        OpenDocument(engine)(tmp_path / "no-existe.pdf")

    assert excinfo.value.path == tmp_path / "no-existe.pdf"
    assert engine.opened == []


def test_ruta_es_un_directorio(tmp_path: Path) -> None:
    engine = FakePdfEngine(make_pages(1))

    with pytest.raises(DocumentAccessError):
        OpenDocument(engine)(tmp_path)

    assert engine.opened == []


def test_archivo_vacio(tmp_path: Path) -> None:
    path = write_file(tmp_path / "vacio.pdf", b"")
    engine = FakePdfEngine(make_pages(1))

    with pytest.raises(UnsupportedDocumentError):
        OpenDocument(engine)(path)


def test_archivo_demasiado_grande(tmp_path: Path) -> None:
    path = write_file(tmp_path / "grande.pdf", b"x" * 32)
    engine = FakePdfEngine(make_pages(1))

    with pytest.raises(DocumentTooLargeError) as excinfo:
        OpenDocument(engine, max_file_size_bytes=16)(path)

    assert excinfo.value.max_size_bytes == 16
    assert engine.opened == []


def test_limite_no_positivo() -> None:
    with pytest.raises(ValueError, match="positivo"):
        OpenDocument(FakePdfEngine(make_pages(1)), max_file_size_bytes=0)
