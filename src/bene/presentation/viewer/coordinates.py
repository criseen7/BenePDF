"""Conversión entre píxeles del lienzo y puntos PDF (RF-006).

El lienzo muestra la página ya rotada por su propia ``/Rotate`` y, encima, la
rotación de vista. Este componente concentra esa transformación para que el
resto de la interfaz trabaje siempre en puntos PDF con origen arriba-izquierda.

``page_width`` y ``page_height`` son las dimensiones **visibles** de la página,
es decir, las de :attr:`bene.domain.models.PageInfo.rotated_size`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from bene.domain.models import VALID_ROTATIONS, PdfRect


@dataclass(frozen=True, slots=True)
class CoordinateMapper:
    """Mapea un punto del lienzo a la página y viceversa."""

    page_width: float
    page_height: float
    scale: float
    view_rotation: int = 0

    def __post_init__(self) -> None:
        if not math.isfinite(self.page_width) or self.page_width <= 0:
            raise ValueError(f"Ancho de página inválido: {self.page_width}")
        if not math.isfinite(self.page_height) or self.page_height <= 0:
            raise ValueError(f"Alto de página inválido: {self.page_height}")
        if not math.isfinite(self.scale) or self.scale <= 0:
            raise ValueError(f"Escala inválida: {self.scale}")
        if self.view_rotation not in VALID_ROTATIONS:
            raise ValueError(f"Rotación de vista inválida: {self.view_rotation}")

    @property
    def view_width(self) -> float:
        if self.view_rotation in (90, 270):
            return self.page_height * self.scale
        return self.page_width * self.scale

    @property
    def view_height(self) -> float:
        if self.view_rotation in (90, 270):
            return self.page_width * self.scale
        return self.page_height * self.scale

    def to_view(self, page_x: float, page_y: float) -> tuple[float, float]:
        """Convierte un punto PDF en coordenadas del lienzo."""
        scale = self.scale
        if self.view_rotation == 90:
            return ((self.page_height - page_y) * scale, page_x * scale)
        if self.view_rotation == 180:
            return ((self.page_width - page_x) * scale, (self.page_height - page_y) * scale)
        if self.view_rotation == 270:
            return (page_y * scale, (self.page_width - page_x) * scale)
        return (page_x * scale, page_y * scale)

    def to_page(self, view_x: float, view_y: float) -> tuple[float, float]:
        """Convierte un punto del lienzo en coordenadas PDF, sin recortar."""
        scale = self.scale
        if self.view_rotation == 90:
            return (view_y / scale, self.page_height - view_x / scale)
        if self.view_rotation == 180:
            return (self.page_width - view_x / scale, self.page_height - view_y / scale)
        if self.view_rotation == 270:
            return (self.page_width - view_y / scale, view_x / scale)
        return (view_x / scale, view_y / scale)

    def to_page_clamped(self, view_x: float, view_y: float) -> tuple[float, float]:
        """Como :meth:`to_page`, pero limita el punto al área de la página."""
        clamped_x = max(0.0, min(view_x, self.view_width))
        clamped_y = max(0.0, min(view_y, self.view_height))
        return self.to_page(clamped_x, clamped_y)

    def rect_to_page(
        self,
        view_x0: float,
        view_y0: float,
        view_x1: float,
        view_y1: float,
    ) -> PdfRect:
        """Convierte un rectángulo del lienzo en un rectángulo PDF normalizado.

        Las esquinas se limitan a la página y el resultado siempre cumple
        ``x1 >= x0`` e ``y1 >= y0``, aunque el arrastre sea hacia atrás.
        """
        first = self.to_page_clamped(view_x0, view_y0)
        second = self.to_page_clamped(view_x1, view_y1)
        return PdfRect(
            min(first[0], second[0]),
            min(first[1], second[1]),
            max(first[0], second[0]),
            max(first[1], second[1]),
        )

    def rect_to_view(self, rect: PdfRect) -> tuple[float, float, float, float]:
        """Convierte un rectángulo PDF en el rectángulo correspondiente del lienzo."""
        first = self.to_view(rect.x0, rect.y0)
        second = self.to_view(rect.x1, rect.y1)
        return (
            min(first[0], second[0]),
            min(first[1], second[1]),
            max(first[0], second[0]),
            max(first[1], second[1]),
        )
