"""Caso de uso: renderizar una página para el visor (RF-002, RNF-002, RNF-003)."""

from __future__ import annotations

import math
from typing import Final

from bene.application.ports.pdf_engine import OpenedDocument, RenderedPage
from bene.domain.errors import PageOutOfRangeError, RenderError
from bene.domain.models import VALID_ROTATIONS

MIN_SCALE: Final[float] = 0.1
MAX_SCALE: Final[float] = 8.0
# El render se pide a escala lógica × densidad de la pantalla. Este margen
# permite renderizar con nitidez en pantallas HiDPI sin aceptar peticiones
# absurdas; el coste real lo limita MAX_RENDER_PIXELS.
MAX_RENDER_SCALE: Final[float] = MAX_SCALE * 8.0
MAX_RENDER_PIXELS: Final[int] = 40_000_000


class RenderPage:
    """Valida la petición antes de llegar al motor y limita el coste del render.

    El límite de píxeles evita que un zoom alto sobre una página grande agote
    la memoria (RNF-006 y sección 11 de los requisitos).
    """

    def __init__(
        self, document: OpenedDocument, *, max_render_pixels: int = MAX_RENDER_PIXELS
    ) -> None:
        if max_render_pixels <= 0:
            raise ValueError("El límite de píxeles debe ser positivo")
        self._document = document
        self._max_render_pixels = max_render_pixels

    def __call__(self, page_index: int, *, scale: float, rotation: int = 0) -> RenderedPage:
        page_count = self._document.info.page_count
        if not 0 <= page_index < page_count:
            raise PageOutOfRangeError(page_index, page_count)

        if rotation not in VALID_ROTATIONS:
            raise ValueError(f"Rotación de vista inválida: {rotation}")

        if not math.isfinite(scale) or not MIN_SCALE <= scale <= MAX_RENDER_SCALE:
            raise ValueError(f"Escala fuera de rango: {scale}")

        width, height = self._document.page_info(page_index).rotated_size
        if width * height * scale * scale > self._max_render_pixels:
            raise RenderError(
                page_index,
                "la resolución solicitada supera el límite de memoria",
            )

        return self._document.render_page(page_index, scale=scale, rotation=rotation)
