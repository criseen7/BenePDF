"""Modelos del dominio, independientes de Qt y de cualquier motor PDF.

Las coordenadas se expresan siempre en **puntos PDF con origen en la esquina
superior izquierda** y sin rotación de vista. La traducción desde píxeles de
pantalla, el zoom y la rotación corresponde a la capa de presentación.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from bene.domain.errors import InvalidGeometryError

VALID_ROTATIONS = (0, 90, 180, 270)


class PageKind(StrEnum):
    """Clasificación orientativa de una página (RF-005)."""

    EMPTY = "empty"
    TEXT = "text"
    GRAPHIC = "graphic"
    SCANNED = "scanned"


@dataclass(frozen=True, slots=True)
class PdfRect:
    """Rectángulo alineado con los ejes en puntos PDF, origen arriba-izquierda.

    Se valida al construirse: las coordenadas deben ser finitas y ``x1``/``y1``
    no pueden ser menores que ``x0``/``y0``. Un rectángulo de área cero es
    válido y se considera vacío.
    """

    x0: float
    y0: float
    x1: float
    y1: float

    def __post_init__(self) -> None:
        coordinates = (self.x0, self.y0, self.x1, self.y1)
        if not all(math.isfinite(value) for value in coordinates):
            raise InvalidGeometryError("Las coordenadas del rectángulo deben ser finitas")
        if self.x1 < self.x0 or self.y1 < self.y0:
            raise InvalidGeometryError(
                "Rectángulo con coordenadas invertidas: "
                f"({self.x0}, {self.y0}, {self.x1}, {self.y1})"
            )

    @classmethod
    def from_size(cls, width: float, height: float, *, x: float = 0.0, y: float = 0.0) -> PdfRect:
        """Crea un rectángulo a partir de su esquina superior izquierda y su tamaño."""
        return cls(x0=x, y0=y, x1=x + width, y1=y + height)

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0

    @property
    def area(self) -> float:
        return self.width * self.height

    @property
    def is_empty(self) -> bool:
        return self.width == 0 or self.height == 0

    def translated(self, dx: float, dy: float) -> PdfRect:
        """Devuelve el rectángulo desplazado, sin mutar el original."""
        return PdfRect(self.x0 + dx, self.y0 + dy, self.x1 + dx, self.y1 + dy)

    def contains(self, x: float, y: float) -> bool:
        """Indica si el punto cae dentro del rectángulo, incluidos sus bordes."""
        return self.x0 <= x <= self.x1 and self.y0 <= y <= self.y1

    def to_tuple(self) -> tuple[float, float, float, float]:
        """Forma en la que el motor PDF recibe el rectángulo."""
        return (self.x0, self.y0, self.x1, self.y1)


@dataclass(frozen=True, slots=True)
class PageInfo:
    """Datos de una página tal como los reporta el motor, en puntos PDF."""

    index: int
    width: float
    height: float
    rotation: int = 0
    kind: PageKind = PageKind.EMPTY
    text_char_count: int = 0
    image_count: int = 0

    def __post_init__(self) -> None:
        if self.index < 0:
            raise ValueError(f"El índice de página no puede ser negativo: {self.index}")
        if self.width <= 0 or self.height <= 0:
            raise InvalidGeometryError(
                f"Dimensiones de página inválidas: {self.width} x {self.height}"
            )
        if self.rotation not in VALID_ROTATIONS:
            raise ValueError(f"Rotación no soportada: {self.rotation}")
        if self.text_char_count < 0 or self.image_count < 0:
            raise ValueError("Los recuentos de texto e imágenes no pueden ser negativos")

    @property
    def rotated_size(self) -> tuple[float, float]:
        """Ancho y alto tal como se ven con la rotación de la página aplicada."""
        if self.rotation in (90, 270):
            return (self.height, self.width)
        return (self.width, self.height)


@dataclass(frozen=True, slots=True)
class DocumentInfo:
    """Resumen de un documento abierto (RF-004 y parte de RF-022)."""

    path: Path
    page_count: int
    file_size_bytes: int
    metadata: Mapping[str, str] = field(default_factory=dict, compare=False, hash=False)
    encrypted: bool = False

    def __post_init__(self) -> None:
        if self.page_count < 1:
            raise ValueError("Un documento debe tener al menos una página")
        if self.file_size_bytes < 0:
            raise ValueError("El tamaño del archivo no puede ser negativo")

    @property
    def title(self) -> str:
        """Título de los metadatos o, si falta, el nombre del archivo."""
        title = self.metadata.get("title", "").strip()
        return title or self.path.stem
