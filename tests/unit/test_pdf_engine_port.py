"""Pruebas del puerto del motor PDF y del DTO de render."""

from __future__ import annotations

from pathlib import Path

import pytest

from bene.application.ports.pdf_engine import (
    BYTES_PER_PIXEL,
    OpenedDocument,
    PdfEngine,
    RenderedPage,
)
from tests.unit.fakes import FakeDocument, FakePdfEngine, make_pages


def make_render(**overrides: object) -> RenderedPage:
    """Render de 4x3 píxeles con valores por defecto válidos."""
    values: dict[str, object] = {
        "page_index": 0,
        "width": 4,
        "height": 3,
        "stride": 4 * BYTES_PER_PIXEL,
        "samples": bytes(4 * 3 * BYTES_PER_PIXEL),
        "scale": 1.0,
        "rotation": 0,
    }
    values.update(overrides)
    return RenderedPage(**values)  # type: ignore[arg-type]


class TestRenderedPage:
    def test_render_valido(self) -> None:
        render = make_render()

        assert render.width * render.height * BYTES_PER_PIXEL == len(render.samples)

    def test_admite_stride_mayor_que_el_ancho(self) -> None:
        render = make_render(stride=16, samples=bytes(16 * 3))

        assert render.stride == 16

    def test_rechaza_stride_insuficiente(self) -> None:
        with pytest.raises(ValueError, match="Stride"):
            make_render(stride=8)

    def test_rechaza_pixeles_incompletos(self) -> None:
        with pytest.raises(ValueError, match="Faltan píxeles"):
            make_render(samples=bytes(10))

    @pytest.mark.parametrize(("width", "height"), [(0, 3), (4, 0), (-4, 3)])
    def test_rechaza_dimensiones_invalidas(self, width: int, height: int) -> None:
        with pytest.raises(ValueError, match="Dimensiones"):
            make_render(width=width, height=height)

    def test_rechaza_escala_no_positiva(self) -> None:
        with pytest.raises(ValueError, match="Escala"):
            make_render(scale=0.0)

    def test_rechaza_rotacion_invalida(self) -> None:
        with pytest.raises(ValueError, match="Rotación"):
            make_render(rotation=45)

    def test_rechaza_indice_negativo(self) -> None:
        with pytest.raises(ValueError, match="Índice"):
            make_render(page_index=-1)


class TestProtocolo:
    def test_el_doble_cumple_el_puerto(self) -> None:
        engine: PdfEngine = FakePdfEngine(make_pages(3))

        document = engine.open_document(Path("documento.pdf"))

        assert isinstance(document, OpenedDocument)
        assert document.info.page_count == 3
        assert document.info.title == "Documento de prueba"
        assert document.page_info(2).index == 2

    def test_el_doble_cierra_el_documento(self) -> None:
        engine = FakePdfEngine(make_pages(1))
        document = engine.open_document(Path("documento.pdf"))

        assert isinstance(document, FakeDocument)
        document.close()
        assert document.closed

    def test_render_respeta_escala_y_rotacion(self) -> None:
        engine = FakePdfEngine(make_pages(1))
        document = engine.open_document(Path("documento.pdf"))

        render = document.render_page(0, scale=2.0, rotation=90)

        assert (render.width, render.height) == (1684, 1190)
        assert render.rotation == 90
        assert len(render.samples) == render.stride * render.height
