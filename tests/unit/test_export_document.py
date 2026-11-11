"""Pruebas del caso de uso de exportación (RF-009, RF-010, RNF-005)."""

from __future__ import annotations

from pathlib import Path

import pytest

from bene.application.use_cases.export_document import ExportDocument
from bene.domain.editing import ImageObject, RedactionObject, StrokeObject, TextObject
from bene.domain.errors import ExportError
from bene.domain.models import DocumentInfo, PdfRect
from bene.domain.pages import PageArrangement
from tests.unit.fakes import FakeDocument, make_pages


def make_document(path: Path) -> FakeDocument:
    info = DocumentInfo(path=path, page_count=3, file_size_bytes=1024)
    return FakeDocument(info, make_pages(3))


def make_objects() -> tuple[TextObject, ImageObject, RedactionObject]:
    return (
        TextObject("texto-1", 0, PdfRect(10, 10, 100, 40), "Hola"),
        ImageObject("imagen-1", 1, PdfRect(0, 0, 50, 50), b"png", "image/png"),
        RedactionObject("redaccion-1", 2, PdfRect(20, 20, 80, 60)),
    )


def test_exporta_y_resume_los_objetos(tmp_path: Path) -> None:
    source = tmp_path / "original.pdf"
    source.write_bytes(b"%PDF-1.7 original")
    document = make_document(source)
    destination = tmp_path / "copia.pdf"
    objects = make_objects()

    result = ExportDocument()(document, destination, objects=objects)

    assert result.destination == destination
    assert result.page_count == 3
    assert result.redaction_count == 1
    assert result.text_count == 1
    assert result.image_count == 1
    assert result.total_objects == 3
    assert destination.read_bytes() == b"%PDF-1.7 exportacion falsa"
    assert document.export_calls == [(destination, objects)]


def test_el_resumen_cuenta_los_trazos(tmp_path: Path) -> None:
    source = tmp_path / "original.pdf"
    source.write_bytes(b"%PDF-1.7 original")
    document = make_document(source)
    stroke = StrokeObject("trazo-1", 0, ((10.0, 10.0), (20.0, 20.0)))

    result = ExportDocument()(document, tmp_path / "copia.pdf", objects=(stroke,))

    assert result.stroke_count == 1
    assert result.total_objects == 1


def test_el_resumen_omite_los_trazos_de_paginas_eliminadas(tmp_path: Path) -> None:
    source = tmp_path / "original.pdf"
    source.write_bytes(b"%PDF-1.7 original")
    document = make_document(source)
    stroke = StrokeObject("trazo-1", 2, ((10.0, 10.0), (20.0, 20.0)))

    result = ExportDocument()(
        document,
        tmp_path / "copia.pdf",
        objects=(stroke,),
        arrangement=PageArrangement(3, order=(0,)),
    )

    assert result.stroke_count == 0
    assert result.total_objects == 0


def test_el_resumen_omite_los_objetos_de_paginas_eliminadas(tmp_path: Path) -> None:
    source = tmp_path / "original.pdf"
    source.write_bytes(b"%PDF-1.7 original")
    document = make_document(source)
    objects = make_objects()

    result = ExportDocument()(
        document,
        tmp_path / "copia.pdf",
        objects=objects,
        arrangement=PageArrangement(3, order=(0,)),
    )

    assert result.page_count == 1
    assert result.text_count == 1
    assert result.image_count == 0
    assert result.redaction_count == 0
    assert result.total_objects == 1


def test_el_original_no_se_modifica(tmp_path: Path) -> None:
    source = tmp_path / "original.pdf"
    original = b"%PDF-1.7 original"
    source.write_bytes(original)
    document = make_document(source)

    ExportDocument()(document, tmp_path / "copia.pdf", objects=make_objects())

    assert source.read_bytes() == original


def test_rechaza_exportar_sobre_el_original(tmp_path: Path) -> None:
    source = tmp_path / "original.pdf"
    source.write_bytes(b"%PDF-1.7 original")
    document = make_document(source)

    with pytest.raises(ExportError, match="distinto del PDF original"):
        ExportDocument()(document, source, objects=())

    assert document.export_calls == []


def test_rechaza_un_destino_que_es_una_carpeta(tmp_path: Path) -> None:
    document = make_document(tmp_path / "original.pdf")

    with pytest.raises(ExportError, match="carpeta"):
        ExportDocument()(document, tmp_path, objects=())


def test_rechaza_una_carpeta_de_destino_inexistente(tmp_path: Path) -> None:
    document = make_document(tmp_path / "original.pdf")

    with pytest.raises(ExportError, match="No existe la carpeta"):
        ExportDocument()(document, tmp_path / "no-existe" / "copia.pdf", objects=())


def test_propaga_el_error_del_motor(tmp_path: Path) -> None:
    document = make_document(tmp_path / "original.pdf")
    document.export_should_fail = True

    with pytest.raises(ExportError, match="simulado"):
        ExportDocument()(document, tmp_path / "copia.pdf", objects=())
