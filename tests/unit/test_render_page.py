"""Pruebas del caso de uso de render."""

from __future__ import annotations

from pathlib import Path

import pytest

from bene.application.ports.pdf_engine import RenderedPage
from bene.application.use_cases.render_page import MAX_RENDER_SCALE, MIN_SCALE, RenderPage
from bene.domain.errors import PageOutOfRangeError, RenderError
from tests.unit.fakes import FakePdfEngine, make_pages


@pytest.fixture
def renderer() -> RenderPage:
    document = FakePdfEngine(make_pages(3)).open_document(Path("documento.pdf"))
    return RenderPage(document)


def test_renderiza_la_pagina_pedida(renderer: RenderPage) -> None:
    result = renderer(1, scale=1.0)

    assert isinstance(result, RenderedPage)
    assert result.page_index == 1
    assert (result.width, result.height) == (595, 842)
    assert len(result.samples) == result.stride * result.height


def test_escala_y_rotacion_de_vista(renderer: RenderPage) -> None:
    result = renderer(0, scale=2.0, rotation=90)

    assert (result.width, result.height) == (1684, 1190)
    assert result.scale == 2.0
    assert result.rotation == 90


@pytest.mark.parametrize("page_index", [-1, 3, 99])
def test_pagina_fuera_de_rango(renderer: RenderPage, page_index: int) -> None:
    with pytest.raises(PageOutOfRangeError):
        renderer(page_index, scale=1.0)


@pytest.mark.parametrize("rotation", [45, 360, -90])
def test_rotacion_invalida(renderer: RenderPage, rotation: int) -> None:
    with pytest.raises(ValueError, match="Rotación"):
        renderer(0, scale=1.0, rotation=rotation)


@pytest.mark.parametrize("scale", [0.0, -1.0, MIN_SCALE / 2, MAX_RENDER_SCALE * 2, float("nan")])
def test_escala_fuera_de_rango(renderer: RenderPage, scale: float) -> None:
    with pytest.raises(ValueError, match="Escala"):
        renderer(0, scale=scale)


def test_admite_escala_de_pantalla_hidpi() -> None:
    """Un zoom lógico alto en una pantalla HiDPI supera MAX_SCALE sin ser un error."""
    document = FakePdfEngine(make_pages(1)).open_document(Path("documento.pdf"))
    renderer = RenderPage(document, max_render_pixels=200_000_000)

    result = renderer(0, scale=16.0)

    assert result.scale == 16.0


def test_limita_los_pixeles_del_render() -> None:
    document = FakePdfEngine(make_pages(1)).open_document(Path("documento.pdf"))
    renderer = RenderPage(document, max_render_pixels=1_000)

    with pytest.raises(RenderError, match="límite"):
        renderer(0, scale=2.0)


def test_limite_de_pixeles_no_positivo() -> None:
    document = FakePdfEngine(make_pages(1)).open_document(Path("documento.pdf"))

    with pytest.raises(ValueError, match="positivo"):
        RenderPage(document, max_render_pixels=0)
