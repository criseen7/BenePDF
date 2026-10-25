"""Pruebas del mapeo entre píxeles de pantalla y puntos PDF (RF-006)."""

from __future__ import annotations

import pytest

from bene.domain.models import PdfRect
from bene.presentation.viewer.coordinates import CoordinateMapper


def mapper(rotation: int = 0, scale: float = 1.0) -> CoordinateMapper:
    return CoordinateMapper(
        page_width=200.0,
        page_height=100.0,
        scale=scale,
        view_rotation=rotation,
    )


class TestDimensiones:
    @pytest.mark.parametrize(
        ("rotation", "expected"),
        [
            (0, (200.0, 100.0)),
            (90, (100.0, 200.0)),
            (180, (200.0, 100.0)),
            (270, (100.0, 200.0)),
        ],
    )
    def test_tamano_visible(self, rotation: int, expected: tuple[float, float]) -> None:
        view = mapper(rotation)

        assert (view.view_width, view.view_height) == expected

    def test_el_zoom_escala_las_dimensiones(self) -> None:
        view = mapper(90, scale=2.0)

        assert (view.view_width, view.view_height) == (200.0, 400.0)

    @pytest.mark.parametrize("scale", [0.0, -1.0, float("nan")])
    def test_rechaza_escala_invalida(self, scale: float) -> None:
        with pytest.raises(ValueError):
            mapper(scale=scale)

    def test_rechaza_rotacion_invalida(self) -> None:
        with pytest.raises(ValueError):
            mapper(45)


class TestIdaYVuelta:
    @pytest.mark.parametrize("rotation", [0, 90, 180, 270])
    @pytest.mark.parametrize("scale", [0.5, 1.0, 2.5])
    def test_el_punto_conserva_sus_coordenadas(self, rotation: int, scale: float) -> None:
        view = mapper(rotation, scale)

        screen_x, screen_y = view.to_view(37.0, 61.0)
        page_x, page_y = view.to_page(screen_x, screen_y)

        assert page_x == pytest.approx(37.0)
        assert page_y == pytest.approx(61.0)

    def test_esquinas_sin_rotacion(self) -> None:
        view = mapper()

        assert view.to_view(0.0, 0.0) == (0.0, 0.0)
        assert view.to_view(200.0, 100.0) == (200.0, 100.0)

    def test_rotacion_90(self) -> None:
        view = mapper(90)

        assert view.to_view(0.0, 0.0) == (100.0, 0.0)
        assert view.to_view(20.0, 10.0) == (90.0, 20.0)
        assert view.to_page(90.0, 20.0) == (20.0, 10.0)

    def test_rotacion_180(self) -> None:
        view = mapper(180)

        assert view.to_view(20.0, 10.0) == (180.0, 90.0)
        assert view.to_page(180.0, 90.0) == (20.0, 10.0)

    def test_rotacion_270(self) -> None:
        view = mapper(270)

        assert view.to_view(20.0, 10.0) == (10.0, 180.0)
        assert view.to_page(10.0, 180.0) == (20.0, 10.0)


class TestRectangulos:
    def test_region_sin_rotacion(self) -> None:
        view = mapper()

        rect = view.rect_to_page(10.0, 20.0, 60.0, 80.0)

        assert rect == PdfRect(10.0, 20.0, 60.0, 80.0)

    def test_region_rotada_90(self) -> None:
        view = mapper(90)

        rect = view.rect_to_page(10.0, 20.0, 60.0, 80.0)

        assert rect == PdfRect(20.0, 40.0, 80.0, 90.0)

    def test_region_rotada_270(self) -> None:
        view = mapper(270)

        rect = view.rect_to_page(10.0, 20.0, 60.0, 80.0)

        assert rect == PdfRect(120.0, 10.0, 180.0, 60.0)

    def test_region_se_normaliza_si_se_arrastra_al_reves(self) -> None:
        view = mapper()

        rect = view.rect_to_page(60.0, 80.0, 10.0, 20.0)

        assert rect == PdfRect(10.0, 20.0, 60.0, 80.0)

    def test_la_region_se_limita_a_la_pagina(self) -> None:
        view = mapper()

        rect = view.rect_to_page(-20.0, -10.0, 250.0, 150.0)

        assert rect == PdfRect(0.0, 0.0, 200.0, 100.0)

    def test_un_punto_fuera_se_limita_a_la_pagina(self) -> None:
        view = mapper(90)

        assert view.to_page_clamped(-10.0, 250.0) == (200.0, 100.0)
