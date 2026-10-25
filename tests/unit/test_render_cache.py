"""Pruebas de la caché acotada de renders (RNF-003)."""

from __future__ import annotations

import pytest

from bene.application.ports.pdf_engine import RenderedPage
from bene.presentation.render_cache import MAX_BYTES, MAX_ENTRIES, RenderCache


def make_render(
    page_index: int = 0,
    *,
    width: int = 10,
    height: int = 10,
    scale: float = 1.0,
    rotation: int = 0,
) -> RenderedPage:
    stride = width * 3
    return RenderedPage(
        page_index=page_index,
        width=width,
        height=height,
        stride=stride,
        samples=b"\x00" * (stride * height),
        scale=scale,
        rotation=rotation,
    )


def render_bytes(width: int = 10, height: int = 10) -> int:
    return width * 3 * height


def test_guarda_y_recupera() -> None:
    cache = RenderCache()
    render = make_render()

    cache.put((0, 1.0, 0), render)

    assert cache.get((0, 1.0, 0)) is render
    assert (0, 1.0, 0) in cache
    assert len(cache) == 1


def test_devuelve_none_si_no_esta() -> None:
    cache = RenderCache()

    assert cache.get((3, 2.0, 90)) is None


def test_desaloja_la_entrada_mas_antigua() -> None:
    cache = RenderCache(max_entries=2)
    cache.put((0, 1.0, 0), make_render(0))
    cache.put((1, 1.0, 0), make_render(1))

    cache.put((2, 1.0, 0), make_render(2))

    assert (0, 1.0, 0) not in cache
    assert (1, 1.0, 0) in cache
    assert (2, 1.0, 0) in cache


def test_get_renueva_la_entrada() -> None:
    cache = RenderCache(max_entries=2)
    cache.put((0, 1.0, 0), make_render(0))
    cache.put((1, 1.0, 0), make_render(1))

    cache.get((0, 1.0, 0))
    cache.put((2, 1.0, 0), make_render(2))

    assert (0, 1.0, 0) in cache
    assert (1, 1.0, 0) not in cache


def test_sustituir_una_entrada_no_duplica_memoria() -> None:
    cache = RenderCache()
    cache.put((0, 1.0, 0), make_render(width=10, height=10))
    cache.put((0, 1.0, 0), make_render(width=20, height=10))

    assert len(cache) == 1
    assert cache.size_bytes == render_bytes(20, 10)


def test_limita_la_memoria_total() -> None:
    entry_bytes = render_bytes(10, 10)
    cache = RenderCache(max_bytes=entry_bytes * 2 + 10)

    for page in range(3):
        cache.put((page, 1.0, 0), make_render(page))

    assert len(cache) == 2
    assert cache.size_bytes <= entry_bytes * 2 + 10
    assert (0, 1.0, 0) not in cache


def test_conserva_la_entrada_mas_reciente_aunque_supere_el_limite() -> None:
    cache = RenderCache(max_bytes=100)

    cache.put((0, 1.0, 0), make_render(width=20, height=20))

    assert len(cache) == 1
    assert cache.size_bytes == render_bytes(20, 20)


def test_clear_vacia_la_cache() -> None:
    cache = RenderCache()
    cache.put((0, 1.0, 0), make_render())

    cache.clear()

    assert len(cache) == 0
    assert cache.size_bytes == 0
    assert (0, 1.0, 0) not in cache


def test_valores_por_defecto() -> None:
    cache = RenderCache()

    assert cache.size_bytes == 0
    assert len(cache) == 0
    assert MAX_ENTRIES > 0
    assert MAX_BYTES > 0


@pytest.mark.parametrize(("max_entries", "max_bytes"), [(0, 1024), (-1, 1024), (1, 0), (1, -1)])
def test_limites_deben_ser_positivos(max_entries: int, max_bytes: int) -> None:
    with pytest.raises(ValueError, match="positivo"):
        RenderCache(max_entries=max_entries, max_bytes=max_bytes)
