"""Cálculos de zoom y ajuste, sin dependencias de Qt (RNF-013)."""

from __future__ import annotations

from enum import StrEnum
from typing import Final

from bene.application.use_cases.render_page import MAX_SCALE, MIN_SCALE

FIT_MARGIN_PX: Final[int] = 16

ZOOM_STEPS: Final[tuple[float, ...]] = (
    0.1,
    0.25,
    0.33,
    0.5,
    0.67,
    0.75,
    1.0,
    1.25,
    1.5,
    2.0,
    2.5,
    3.0,
    4.0,
    6.0,
    8.0,
)


class FitMode(StrEnum):
    NONE = "none"
    WIDTH = "width"
    PAGE = "page"


def clamp_scale(scale: float, *, minimum: float = MIN_SCALE, maximum: float = MAX_SCALE) -> float:
    return max(minimum, min(maximum, scale))


def rotated_size(width: float, height: float, rotation: int) -> tuple[float, float]:
    """Dimensiones visibles tras aplicar la rotación de vista."""
    if rotation % 180 == 90:
        return (height, width)
    return (width, height)


def fit_scale(
    viewport: tuple[int, int],
    page: tuple[float, float],
    *,
    mode: FitMode,
    margin: int = FIT_MARGIN_PX,
) -> float:
    """Escala que hace que la página quepa en el visor.

    ``viewport`` son píxeles disponibles y ``page`` puntos PDF; con ``scale`` a
    72 ppp un punto equivale a un píxel, así que la división es directa.
    """
    if mode is FitMode.NONE:
        raise ValueError("El modo de ajuste no puede ser NONE")

    available_width = max(viewport[0] - margin * 2, 1)
    available_height = max(viewport[1] - margin * 2, 1)
    page_width, page_height = page
    if page_width <= 0 or page_height <= 0:
        raise ValueError("La página no tiene dimensiones válidas")

    width_scale = available_width / page_width
    if mode is FitMode.WIDTH:
        return clamp_scale(width_scale)
    height_scale = available_height / page_height
    return clamp_scale(min(width_scale, height_scale))


def next_zoom(current: float, *, direction: int) -> float:
    """Siguiente escala de la lista, sin salirse del rango."""
    if direction > 0:
        for step in ZOOM_STEPS:
            if step > current + 1e-6:
                return step
        return clamp_scale(current)
    if direction < 0:
        for step in reversed(ZOOM_STEPS):
            if step < current - 1e-6:
                return step
        return clamp_scale(current)
    return clamp_scale(current)
