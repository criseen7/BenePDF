"""Pruebas de los cálculos de zoom y ajuste (RNF-013)."""

from __future__ import annotations

import pytest

from bene.application.use_cases.render_page import MAX_SCALE, MIN_SCALE
from bene.presentation.fit import (
    FIT_MARGIN_PX,
    ZOOM_STEPS,
    FitMode,
    clamp_scale,
    fit_scale,
    next_zoom,
    rotated_size,
)


class TestRotatedSize:
    @pytest.mark.parametrize(
        ("rotation", "expected"),
        [(0, (595.0, 842.0)), (90, (842.0, 595.0)), (180, (595.0, 842.0)), (270, (842.0, 595.0))],
    )
    def test_intercambia_ancho_y_alto(self, rotation: int, expected: tuple[float, float]) -> None:
        assert rotated_size(595.0, 842.0, rotation) == expected

    def test_normaliza_angulos_fuera_de_rango(self) -> None:
        assert rotated_size(10.0, 20.0, 450) == (20.0, 10.0)


class TestFitScale:
    def test_ajustar_pagina_usa_el_lado_mas_estrecho(self) -> None:
        scale = fit_scale((816, 1053), (595.0, 842.0), mode=FitMode.PAGE)

        # (1053 - 32) / 842 es menor que (816 - 32) / 595.
        assert scale == pytest.approx((1053 - 2 * FIT_MARGIN_PX) / 842.0)

    def test_ajustar_ancho_ignora_la_altura(self) -> None:
        scale = fit_scale((816, 1053), (595.0, 842.0), mode=FitMode.WIDTH)

        assert scale == pytest.approx((816 - 2 * FIT_MARGIN_PX) / 595.0)

    def test_respeta_el_margen_indicado(self) -> None:
        scale = fit_scale((100, 100), (20.0, 20.0), mode=FitMode.PAGE, margin=0)

        assert scale == pytest.approx(5.0)

    def test_limita_la_escala_minima(self) -> None:
        scale = fit_scale((816, 1053), (10_000.0, 10_000.0), mode=FitMode.PAGE)

        assert scale == MIN_SCALE

    def test_limita_la_escala_maxima(self) -> None:
        scale = fit_scale((816, 1053), (10.0, 10.0), mode=FitMode.PAGE)

        assert scale == MAX_SCALE

    def test_visor_mas_pequeno_que_los_margenes(self) -> None:
        scale = fit_scale((10, 10), (2.0, 2.0), mode=FitMode.PAGE)

        assert scale == pytest.approx(0.5)

    def test_modo_none_no_tiene_escala(self) -> None:
        with pytest.raises(ValueError, match="NONE"):
            fit_scale((816, 1053), (595.0, 842.0), mode=FitMode.NONE)

    @pytest.mark.parametrize("page", [(0.0, 842.0), (595.0, 0.0), (-1.0, 842.0)])
    def test_pagina_sin_dimensiones_validas(self, page: tuple[float, float]) -> None:
        with pytest.raises(ValueError, match="dimensiones"):
            fit_scale((816, 1053), page, mode=FitMode.PAGE)


class TestNextZoom:
    def test_acerca_al_siguiente_paso(self) -> None:
        assert next_zoom(1.0, direction=1) == 1.25

    def test_aleja_al_paso_anterior(self) -> None:
        assert next_zoom(1.0, direction=-1) == 0.75

    def test_usa_el_siguiente_paso_desde_un_valor_intermedio(self) -> None:
        assert next_zoom(0.3, direction=1) == 0.33
        assert next_zoom(0.3, direction=-1) == 0.25

    def test_no_supera_el_maximo(self) -> None:
        assert next_zoom(MAX_SCALE, direction=1) == MAX_SCALE
        assert next_zoom(100.0, direction=1) == MAX_SCALE

    def test_no_baja_del_minimo(self) -> None:
        assert next_zoom(MIN_SCALE, direction=-1) == MIN_SCALE
        assert next_zoom(0.0, direction=-1) == MIN_SCALE

    def test_direccion_cero_conserva_la_escala(self) -> None:
        assert next_zoom(1.5, direction=0) == 1.5

    def test_todos_los_pasos_son_crecientes_y_validos(self) -> None:
        assert tuple(sorted(ZOOM_STEPS)) == ZOOM_STEPS
        assert ZOOM_STEPS[0] == MIN_SCALE
        assert ZOOM_STEPS[-1] == MAX_SCALE


class TestClampScale:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [(0.01, MIN_SCALE), (MIN_SCALE, MIN_SCALE), (1.0, 1.0), (MAX_SCALE, MAX_SCALE)],
    )
    def test_limita_al_rango(self, value: float, expected: float) -> None:
        assert clamp_scale(value) == expected
