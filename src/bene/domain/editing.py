"""Modelos y comandos inmutables de edición (ADR-002, RF-007 a RF-014, RF-026).

Las coordenadas son puntos PDF en el espacio visible de la página, con origen
arriba-izquierda. El documento original nunca se modifica: los comandos se
aplican a un estado en memoria y solo se materializarán al exportar.

Los comandos son valores inmutables. :func:`apply_command` recibe el estado
anterior y devuelve uno nuevo, de modo que deshacer y rehacer solo consistan en
mover el índice del historial y reconstruir el estado.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from enum import StrEnum
from pathlib import Path
from typing import Final

from bene.domain.errors import EditObjectNotFoundError, InvalidEditOperationError
from bene.domain.models import VALID_ROTATIONS, PdfRect
from bene.domain.pages import PageArrangement

SUPPORTED_FONTS: Final[tuple[str, ...]] = (
    "Helvetica",
    "Times-Roman",
    "Courier",
)

SUPPORTED_IMAGE_TYPES: Final[tuple[str, ...]] = (
    "image/png",
    "image/jpeg",
)

_HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


class TextAlignment(StrEnum):
    """Alineación horizontal del texto dentro de su cuadro."""

    LEFT = "left"
    CENTER = "center"
    RIGHT = "right"


@dataclass(frozen=True, slots=True)
class TextStyle:
    """Fuente, tamaño, color y alineación de un cuadro de texto."""

    font_name: str = "Helvetica"
    font_size: float = 12.0
    color: str = "#000000"
    alignment: TextAlignment = TextAlignment.LEFT

    def __post_init__(self) -> None:
        if not self.font_name.strip():
            raise ValueError("La fuente no puede estar vacía")
        if not math.isfinite(self.font_size) or self.font_size <= 0:
            raise ValueError(f"Tamaño de fuente inválido: {self.font_size}")
        if not _HEX_COLOR.match(self.color):
            raise ValueError(f"Color no válido: {self.color!r}; se espera #rrggbb")
        object.__setattr__(self, "alignment", TextAlignment(self.alignment))


@dataclass(frozen=True, slots=True)
class StrokeStyle:
    """Color y grosor de un trazo libre."""

    color: str = "#000000"
    width: float = 2.0

    def __post_init__(self) -> None:
        if not _HEX_COLOR.match(self.color):
            raise ValueError(f"Color no válido: {self.color!r}; se espera #rrggbb")
        if not math.isfinite(self.width) or self.width <= 0:
            raise ValueError(f"Grosor de trazo inválido: {self.width}")


def _validate_identity(object_id: str, page_index: int, rect: PdfRect) -> None:
    if not object_id.strip():
        raise ValueError("El identificador del objeto no puede estar vacío")
    if page_index < 0:
        raise ValueError(f"El índice de página no puede ser negativo: {page_index}")
    if rect.is_empty:
        raise ValueError("El rectángulo del objeto no puede estar vacío")


@dataclass(frozen=True, slots=True)
class TextObject:
    """Cuadro de texto añadido a una página."""

    object_id: str
    page_index: int
    rect: PdfRect
    text: str
    style: TextStyle = field(default_factory=TextStyle)

    def __post_init__(self) -> None:
        _validate_identity(self.object_id, self.page_index, self.rect)
        if not self.text.strip():
            raise ValueError("El texto no puede estar vacío")


@dataclass(frozen=True, slots=True)
class StrokeObject:
    """Trazo libre dibujado sobre una página (RF-026).

    Los puntos están en coordenadas visibles de la página, con origen
    arriba-izquierda. El rectángulo se calcula a partir de la caja de los puntos
    y del grosor, de modo que un punto aislado o una línea recta también se
    puedan seleccionar.
    """

    object_id: str
    page_index: int
    points: tuple[tuple[float, float], ...]
    style: StrokeStyle = field(default_factory=StrokeStyle)

    def __post_init__(self) -> None:
        if not self.points:
            raise ValueError("El trazo debe tener al menos un punto")
        normalized: list[tuple[float, float]] = []
        for point in self.points:
            try:
                x, y = point
            except (TypeError, ValueError):
                raise ValueError(f"Punto de trazo inválido: {point!r}") from None
            if not math.isfinite(x) or not math.isfinite(y):
                raise ValueError(f"Las coordenadas del trazo deben ser finitas: {point!r}")
            normalized.append((float(x), float(y)))
        object.__setattr__(self, "points", tuple(normalized))
        _validate_identity(self.object_id, self.page_index, self.rect)

    @property
    def rect(self) -> PdfRect:
        """Caja visible que ocupa el trazo, incluido su grosor."""
        xs = [x for x, _ in self.points]
        ys = [y for _, y in self.points]
        padding = self.style.width / 2.0
        return PdfRect(
            min(xs) - padding,
            min(ys) - padding,
            max(xs) + padding,
            max(ys) + padding,
        )


@dataclass(frozen=True, slots=True)
class ImageObject:
    """Imagen añadida a una página, con sus datos para la vista previa."""

    object_id: str
    page_index: int
    rect: PdfRect
    data: bytes
    mime_type: str
    source_path: Path | None = None

    def __post_init__(self) -> None:
        _validate_identity(self.object_id, self.page_index, self.rect)
        if not self.data:
            raise ValueError("La imagen no tiene datos")
        if self.mime_type not in SUPPORTED_IMAGE_TYPES:
            raise ValueError(f"Tipo de imagen no soportado: {self.mime_type}")


@dataclass(frozen=True, slots=True)
class ImageReplacementObject:
    """Sustituye una imagen ya incrustada en el PDF (RF-013).

    ``image_id`` es un identificador opaco que entrega el motor PDF; la capa de
    dominio no interpreta su formato. ``rect`` es la región visible que ocupaba
    la imagen original y se usa para la vista previa.
    """

    object_id: str
    page_index: int
    image_id: str
    rect: PdfRect
    data: bytes
    mime_type: str
    source_path: Path | None = None

    def __post_init__(self) -> None:
        _validate_identity(self.object_id, self.page_index, self.rect)
        if not self.image_id.strip():
            raise ValueError("El identificador de la imagen original no puede estar vacío")
        if not self.data:
            raise ValueError("La imagen de reemplazo no tiene datos")
        if self.mime_type not in SUPPORTED_IMAGE_TYPES:
            raise ValueError(f"Tipo de imagen no soportado: {self.mime_type}")


@dataclass(frozen=True, slots=True)
class RedactionObject:
    """Región marcada para eliminar de forma permanente al exportar.

    La vista previa la dibuja el lienzo; el contenido subyacente solo
    desaparece cuando se materializa la exportación (RN-003, RNF-008).
    """

    object_id: str
    page_index: int
    rect: PdfRect

    def __post_init__(self) -> None:
        _validate_identity(self.object_id, self.page_index, self.rect)


EditObject = TextObject | StrokeObject | ImageObject | ImageReplacementObject | RedactionObject


@dataclass(frozen=True, slots=True)
class AddTextCommand:
    """Añade un cuadro de texto."""

    text_object: TextObject


@dataclass(frozen=True, slots=True)
class AddImageCommand:
    """Añade una imagen."""

    image_object: ImageObject


@dataclass(frozen=True, slots=True)
class AddStrokeCommand:
    """Añade un trazo libre."""

    stroke_object: StrokeObject


@dataclass(frozen=True, slots=True)
class AddRedactionCommand:
    """Marca una región para redactarla al exportar."""

    redaction_object: RedactionObject


@dataclass(frozen=True, slots=True)
class AddImageReplacementCommand:
    """Sustituye una imagen incrustada del PDF."""

    replacement: ImageReplacementObject


@dataclass(frozen=True, slots=True)
class MoveObjectCommand:
    """Mueve un objeto a un rectángulo absoluto de la misma página."""

    object_id: str
    page_index: int
    rect: PdfRect

    def __post_init__(self) -> None:
        _validate_transform(self.object_id, self.page_index, self.rect)


@dataclass(frozen=True, slots=True)
class ResizeObjectCommand:
    """Cambia el tamaño (y opcionalmente la posición) de un objeto."""

    object_id: str
    page_index: int
    rect: PdfRect

    def __post_init__(self) -> None:
        _validate_transform(self.object_id, self.page_index, self.rect)


@dataclass(frozen=True, slots=True)
class DeleteObjectCommand:
    """Elimina un objeto añadido durante la sesión."""

    object_id: str
    page_index: int

    def __post_init__(self) -> None:
        if not self.object_id.strip():
            raise ValueError("El identificador del objeto no puede estar vacío")
        if self.page_index < 0:
            raise ValueError(f"El índice de página no puede ser negativo: {self.page_index}")


@dataclass(frozen=True, slots=True)
class RotatePageCommand:
    """Acumula una rotación adicional a una página fuente."""

    page_index: int
    degrees: int

    def __post_init__(self) -> None:
        if self.page_index < 0:
            raise ValueError(f"El índice de página no puede ser negativo: {self.page_index}")
        if self.degrees not in VALID_ROTATIONS:
            raise ValueError(f"Rotación de página no soportada: {self.degrees}")


@dataclass(frozen=True, slots=True)
class MovePageCommand:
    """Mueve una página entre dos posiciones de salida."""

    from_position: int
    to_position: int

    def __post_init__(self) -> None:
        if self.from_position < 0 or self.to_position < 0:
            raise ValueError("Las posiciones de página no pueden ser negativas")


@dataclass(frozen=True, slots=True)
class DeletePageCommand:
    """Elimina una página fuente de la copia de trabajo."""

    page_index: int

    def __post_init__(self) -> None:
        if self.page_index < 0:
            raise ValueError(f"El índice de página no puede ser negativo: {self.page_index}")


def _validate_transform(object_id: str, page_index: int, rect: PdfRect) -> None:
    if not object_id.strip():
        raise ValueError("El identificador del objeto no puede estar vacío")
    if page_index < 0:
        raise ValueError(f"El índice de página no puede ser negativo: {page_index}")
    if rect.is_empty:
        raise ValueError("El rectángulo del objeto no puede estar vacío")


ObjectCommand = (
    AddTextCommand
    | AddStrokeCommand
    | AddImageCommand
    | AddRedactionCommand
    | AddImageReplacementCommand
    | MoveObjectCommand
    | ResizeObjectCommand
    | DeleteObjectCommand
)

PageCommand = RotatePageCommand | MovePageCommand | DeletePageCommand

EditCommand = ObjectCommand | PageCommand

PAGE_COMMANDS = (RotatePageCommand, MovePageCommand, DeletePageCommand)


def apply_command(
    objects: Mapping[str, EditObject], command: ObjectCommand
) -> dict[str, EditObject]:
    """Aplica un comando y devuelve el nuevo estado, sin mutar ``objects``.

    Errores esperados: :class:`EditObjectNotFoundError` si el objeto no existe
    y :class:`InvalidEditOperationError` si el comando contradice el estado.
    """
    updated = dict(objects)

    if isinstance(command, AddTextCommand):
        _add(updated, command.text_object)
    elif isinstance(command, AddStrokeCommand):
        _add(updated, command.stroke_object)
    elif isinstance(command, AddImageCommand):
        _add(updated, command.image_object)
    elif isinstance(command, AddRedactionCommand):
        _add(updated, command.redaction_object)
    elif isinstance(command, AddImageReplacementCommand):
        _add(updated, command.replacement)
    elif isinstance(command, (MoveObjectCommand, ResizeObjectCommand)):
        current = _require(updated, command.object_id)
        if current.page_index != command.page_index:
            raise InvalidEditOperationError(
                f"El objeto {command.object_id!r} pertenece a la página "
                f"{current.page_index + 1}, no a la {command.page_index + 1}"
            )
        if isinstance(current, StrokeObject):
            updated[command.object_id] = _transform_stroke(
                current,
                command.rect,
                resize=isinstance(command, ResizeObjectCommand),
            )
        else:
            updated[command.object_id] = replace(current, rect=command.rect)
    elif isinstance(command, DeleteObjectCommand):
        current = _require(updated, command.object_id)
        if current.page_index != command.page_index:
            raise InvalidEditOperationError(
                f"El objeto {command.object_id!r} pertenece a la página "
                f"{current.page_index + 1}, no a la {command.page_index + 1}"
            )
        del updated[command.object_id]

    return updated


def _transform_stroke(obj: StrokeObject, target: PdfRect, *, resize: bool) -> StrokeObject:
    """Mueve o redimensiona un trazo transformando sus puntos."""
    current = obj.rect
    if not resize:
        dx = target.x0 - current.x0
        dy = target.y0 - current.y0
        points = tuple((x + dx, y + dy) for x, y in obj.points)
        return replace(obj, points=points)

    padding = obj.style.width / 2.0
    old_inner = _inset_rect(current, padding)
    new_inner = _inset_rect(target, padding)
    scale_x = new_inner.width / old_inner.width if old_inner.width > 0 else 1.0
    scale_y = new_inner.height / old_inner.height if old_inner.height > 0 else 1.0
    points = tuple(
        (
            new_inner.x0 + (x - old_inner.x0) * scale_x,
            new_inner.y0 + (y - old_inner.y0) * scale_y,
        )
        for x, y in obj.points
    )
    return replace(obj, points=points)


def _inset_rect(rect: PdfRect, amount: float) -> PdfRect:
    """Reduce un rectángulo sin cruzar su centro."""
    horizontal = min(amount, rect.width / 2.0)
    vertical = min(amount, rect.height / 2.0)
    return PdfRect(
        rect.x0 + horizontal,
        rect.y0 + vertical,
        rect.x1 - horizontal,
        rect.y1 - vertical,
    )


def _add(objects: dict[str, EditObject], obj: EditObject) -> None:
    if obj.object_id in objects:
        raise InvalidEditOperationError(
            f"Ya existe un objeto con el identificador {obj.object_id!r}"
        )
    objects[obj.object_id] = obj


def _require(objects: Mapping[str, EditObject], object_id: str) -> EditObject:
    try:
        return objects[object_id]
    except KeyError:
        raise EditObjectNotFoundError(object_id) from None


def apply_page_command(arrangement: PageArrangement, command: PageCommand) -> PageArrangement:
    """Aplica un comando de página y devuelve una disposición nueva.

    Errores esperados: :class:`InvalidEditOperationError` si la página no está
    presente o la operación dejaría el documento sin páginas.
    """
    if isinstance(command, RotatePageCommand):
        return arrangement.rotated(command.page_index, command.degrees)
    if isinstance(command, MovePageCommand):
        return arrangement.moved(command.from_position, command.to_position)
    if isinstance(command, DeletePageCommand):
        return arrangement.without(command.page_index)
    raise InvalidEditOperationError(f"Comando de página no soportado: {command!r}")
