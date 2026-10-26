"""Pruebas de los errores de dominio."""

from __future__ import annotations

from pathlib import Path

from bene.domain.errors import (
    BeneError,
    DocumentAccessError,
    DocumentNotFoundError,
    EncryptedDocumentError,
    ExportError,
    InvalidGeometryError,
    PageOutOfRangeError,
    RenderError,
    UnsupportedDocumentError,
)


def test_errores_de_documento_incluyen_la_ruta() -> None:
    path = Path("C:/documentos/informe.pdf")

    for error in (
        DocumentNotFoundError(path),
        DocumentAccessError(path),
        UnsupportedDocumentError(path),
    ):
        assert isinstance(error, BeneError)
        assert error.path == path
        assert str(path) in str(error)


def test_documento_cifrado_sin_contrasena() -> None:
    error = EncryptedDocumentError(Path("secreto.pdf"))

    assert error.wrong_password is False
    assert "requiere contraseña" in str(error)


def test_documento_cifrado_con_contrasena_incorrecta() -> None:
    error = EncryptedDocumentError(Path("secreto.pdf"), wrong_password=True)

    assert error.wrong_password is True
    assert "no es correcta" in str(error)


def test_pagina_fuera_de_rango_es_index_error() -> None:
    error = PageOutOfRangeError(page_index=5, page_count=3)

    assert isinstance(error, IndexError)
    assert error.page_index == 5
    assert error.page_count == 3
    assert "página 6" in str(error)
    assert "3 páginas" in str(error)


def test_error_de_render_incluye_pagina_y_motivo() -> None:
    error = RenderError(page_index=0, reason="página corrupta")

    assert error.reason == "página corrupta"
    assert "página 1" in str(error)
    assert "página corrupta" in str(error)


def test_error_de_geometria_es_value_error() -> None:
    assert isinstance(InvalidGeometryError("x"), ValueError)
    assert isinstance(InvalidGeometryError("x"), BeneError)


def test_error_de_exportacion_conserva_el_mensaje() -> None:
    error = ExportError("No se pudo escribir la copia")

    assert isinstance(error, BeneError)
    assert error.message == "No se pudo escribir la copia"
    assert "No se pudo escribir" in str(error)
