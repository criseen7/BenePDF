"""Modelos y comandos inmutables de edición (ADR-002, RF-007 a RF-014).

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
from bene.domain.models import PdfRect

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


EditObject = TextObject | ImageObject


@dataclass(frozen=True, slots=True)
class AddTextCommand:
    """Añade un cuadro de texto."""

    text_object: TextObject


@dataclass(frozen=True, slots=True)
class AddImageCommand:
    """Añade una imagen."""

    image_object: ImageObject


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


def _validate_transform(object_id: str, page_index: int, rect: PdfRect) -> None:
    if not object_id.strip():
        raise ValueError("El identificador del objeto no puede estar vacío")
    if page_index < 0:
        raise ValueError(f"El índice de página no puede ser negativo: {page_index}")
    if rect.is_empty:
        raise ValueError("El rectángulo del objeto no puede estar vacío")


EditCommand = (
    AddTextCommand | AddImageCommand | MoveObjectCommand | ResizeObjectCommand | DeleteObjectCommand
)


def apply_command(objects: Mapping[str, EditObject], command: EditCommand) -> dict[str, EditObject]:
    """Aplica un comando y devuelve el nuevo estado, sin mutar ``objects``.

    Errores esperados: :class:`EditObjectNotFoundError` si el objeto no existe
    y :class:`InvalidEditOperationError` si el comando contradice el estado.
    """
    updated = dict(objects)

    if isinstance(command, AddTextCommand):
        _add(updated, command.text_object)
    elif isinstance(command, AddImageCommand):
        _add(updated, command.image_object)
    elif isinstance(command, (MoveObjectCommand, ResizeObjectCommand)):
        current = _require(updated, command.object_id)
        if current.page_index != command.page_index:
            raise InvalidEditOperationError(
                f"El objeto {command.object_id!r} pertenece a la página "
                f"{current.page_index + 1}, no a la {command.page_index + 1}"
            )
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
