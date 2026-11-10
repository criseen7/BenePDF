"""Disposición de las páginas de la sesión de edición (RF-021).

El PDF original nunca se modifica. La disposición guarda qué páginas del
documento fuente se exportarán, en qué orden y con qué rotación adicional. Los
índices de :attr:`PageArrangement.order` y de :attr:`PageArrangement.rotations`
son **índices del documento fuente** (base cero), no posiciones de salida: así
los objetos de edición siguen apuntando siempre a la página original aunque el
usuario reordene o elimine páginas.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from types import MappingProxyType

from bene.domain.errors import InvalidEditOperationError, PageOutOfRangeError
from bene.domain.models import VALID_ROTATIONS

_PAGE_SELECTION_PART = re.compile(r"^\s*(\d+)\s*(?:-\s*(\d+)\s*)?$")


@dataclass(frozen=True, slots=True)
class PageArrangement:
    """Páginas visibles y rotación adicional de cada página fuente.

    ``page_count`` es el número de páginas del documento original. ``order``
    contiene los índices fuente que se exportarán, en el orden de salida. Las
    páginas ausentes de ``order`` se consideran eliminadas de la copia de
    trabajo. ``rotations`` guarda solo las rotaciones adicionales distintas de
    cero, en múltiplos de 90 grados.
    """

    page_count: int
    order: tuple[int, ...]
    rotations: Mapping[int, int] = field(default_factory=dict, hash=False)

    def __post_init__(self) -> None:
        if self.page_count < 0:
            raise ValueError(f"El número de páginas no puede ser negativo: {self.page_count}")

        if self.page_count == 0:
            if self.order:
                raise ValueError("Un documento sin páginas no puede tener un orden")
        else:
            if not self.order:
                raise ValueError("El orden de páginas no puede estar vacío")
            if len(set(self.order)) != len(self.order):
                raise ValueError("El orden de páginas no puede contener duplicados")
            for source_index in self.order:
                if not 0 <= source_index < self.page_count:
                    raise PageOutOfRangeError(source_index, self.page_count)

        rotations = dict(self.rotations)
        for source_index, degrees in rotations.items():
            if not 0 <= source_index < self.page_count:
                raise PageOutOfRangeError(source_index, self.page_count)
            if degrees not in VALID_ROTATIONS:
                raise ValueError(f"Rotación de página no soportada: {degrees}")
        # Se expone como vista de solo lectura para que el estado congelado no
        # pueda mutarse desde fuera del dominio.
        object.__setattr__(self, "rotations", MappingProxyType(rotations))

    @classmethod
    def initial(cls, page_count: int) -> PageArrangement:
        """Disposición identidad: todas las páginas, sin rotación adicional."""
        return cls(page_count=page_count, order=tuple(range(page_count)))

    @property
    def output_page_count(self) -> int:
        return len(self.order)

    def source_index(self, output_index: int) -> int:
        """Índice fuente de la página que ocupa ``output_index`` en la salida."""
        if not 0 <= output_index < len(self.order):
            raise PageOutOfRangeError(output_index, len(self.order))
        return self.order[output_index]

    def output_index(self, source_index: int) -> int | None:
        """Posición de salida de una página fuente, o ``None`` si está eliminada."""
        try:
            return self.order.index(source_index)
        except ValueError:
            return None

    def is_present(self, source_index: int) -> bool:
        return source_index in self.order

    def rotation(self, source_index: int) -> int:
        """Rotación adicional de la página fuente, en grados."""
        if not 0 <= source_index < self.page_count:
            raise PageOutOfRangeError(source_index, self.page_count)
        return self.rotations.get(source_index, 0) % 360

    def rotated(self, source_index: int, degrees: int) -> PageArrangement:
        """Acumula una rotación adicional a una página presente."""
        self._require_present(source_index)
        if degrees not in VALID_ROTATIONS:
            raise InvalidEditOperationError(
                f"Rotación de página no soportada: {degrees}; usa 0, 90, 180 o 270"
            )
        total = (self.rotation(source_index) + degrees) % 360
        rotations = dict(self.rotations)
        if total:
            rotations[source_index] = total
        else:
            rotations.pop(source_index, None)
        return replace(self, rotations=rotations)

    def moved(self, from_position: int, to_position: int) -> PageArrangement:
        """Mueve una página entre posiciones de salida."""
        self._require_output_position(from_position)
        self._require_output_position(to_position)
        order = list(self.order)
        page = order.pop(from_position)
        order.insert(to_position, page)
        return replace(self, order=tuple(order))

    def without(self, source_index: int) -> PageArrangement:
        """Elimina una página fuente de la copia de trabajo."""
        self._require_present(source_index)
        if len(self.order) <= 1:
            raise InvalidEditOperationError("No se puede eliminar la última página del documento")
        order = tuple(index for index in self.order if index != source_index)
        rotations = {key: value for key, value in self.rotations.items() if key != source_index}
        return replace(self, order=order, rotations=rotations)

    def subset(self, source_indices: Iterable[int]) -> PageArrangement:
        """Disposición con solo las páginas indicadas, conservando su orden.

        Se usa para extraer páginas a un archivo nuevo sin alterar la sesión.
        """
        selected = tuple(source_indices)
        if not selected:
            raise InvalidEditOperationError("Selecciona al menos una página para extraer")
        if len(set(selected)) != len(selected):
            raise InvalidEditOperationError("La selección de páginas no puede tener duplicados")
        for source_index in selected:
            self._require_present(source_index)
        rotations = {key: value for key, value in self.rotations.items() if key in set(selected)}
        return PageArrangement(self.page_count, selected, rotations)

    def _require_present(self, source_index: int) -> None:
        if not 0 <= source_index < self.page_count:
            raise PageOutOfRangeError(source_index, self.page_count)
        if source_index not in self.order:
            raise InvalidEditOperationError(
                f"La página {source_index + 1} está eliminada de la copia de trabajo"
            )

    def _require_output_position(self, position: int) -> None:
        if not 0 <= position < len(self.order):
            raise PageOutOfRangeError(position, len(self.order))


def parse_page_selection(text: str, page_count: int) -> tuple[int, ...]:
    """Convierte una selección como ``1-3, 5`` en índices fuente ordenados.

    La entrada usa números de página **base uno**, que es lo que ve el usuario.
    El resultado no tiene duplicados y sigue el orden del documento.
    """
    if page_count < 1:
        raise InvalidEditOperationError("El documento no tiene páginas")
    if not text.strip():
        raise InvalidEditOperationError("Escribe al menos una página o un rango")

    selected: set[int] = set()
    for part in text.split(","):
        match = _PAGE_SELECTION_PART.match(part)
        if match is None:
            raise InvalidEditOperationError(
                f"Selección de páginas no válida: {part.strip()!r}; usa por ejemplo 1-3, 5"
            )
        start = int(match.group(1))
        end = int(match.group(2)) if match.group(2) is not None else start
        if start < 1 or end < 1:
            raise InvalidEditOperationError("Los números de página empiezan en 1")
        if start > end:
            raise InvalidEditOperationError(
                f"Rango invertido: {start}-{end}; el primer número debe ser menor o igual"
            )
        if end > page_count:
            raise InvalidEditOperationError(
                f"La página {end} no existe; el documento tiene {page_count} páginas"
            )
        selected.update(range(start - 1, end))

    return tuple(sorted(selected))
