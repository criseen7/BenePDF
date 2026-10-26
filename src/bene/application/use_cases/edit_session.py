"""Sesión de edición con historial de comandos (ADR-002, RF-014).

La sesión mantiene la lista completa de comandos y un índice que separa los
activos de los que se pueden rehacer. El estado visible se reconstruye
aplicando solo los comandos activos, así que deshacer y rehacer no puede dejar
el documento en un estado intermedio inconsistente.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from bene.domain.editing import (
    AddImageCommand,
    AddRedactionCommand,
    AddTextCommand,
    DeleteObjectCommand,
    EditCommand,
    EditObject,
    ImageObject,
    MoveObjectCommand,
    RedactionObject,
    ResizeObjectCommand,
    TextObject,
    TextStyle,
    apply_command,
)
from bene.domain.errors import EditObjectNotFoundError
from bene.domain.models import PdfRect

IdFactory = Callable[[str], str]


class EditHistory:
    """Lista de comandos con un índice de deshacer/rehacer."""

    def __init__(self) -> None:
        self._commands: list[EditCommand] = []
        self._index = 0

    @property
    def commands(self) -> tuple[EditCommand, ...]:
        return tuple(self._commands)

    @property
    def index(self) -> int:
        return self._index

    @property
    def active_commands(self) -> tuple[EditCommand, ...]:
        return tuple(self._commands[: self._index])

    @property
    def can_undo(self) -> bool:
        return self._index > 0

    @property
    def can_redo(self) -> bool:
        return self._index < len(self._commands)

    def push(self, command: EditCommand) -> None:
        """Añade un comando y descarta el futuro que hubiera para rehacer."""
        del self._commands[self._index :]
        self._commands.append(command)
        self._index = len(self._commands)

    def undo(self) -> EditCommand | None:
        if not self.can_undo:
            return None
        self._index -= 1
        return self._commands[self._index]

    def redo(self) -> EditCommand | None:
        if not self.can_redo:
            return None
        command = self._commands[self._index]
        self._index += 1
        return command

    def clear(self) -> None:
        self._commands.clear()
        self._index = 0


class EditSession:
    """Edición en memoria de un documento, con identificadores estables."""

    def __init__(self, *, id_factory: IdFactory | None = None) -> None:
        self._history = EditHistory()
        self._objects: dict[str, EditObject] = {}
        self._id_factory = id_factory or self._default_id
        self._counters: dict[str, int] = {}
        self._saved_commands: tuple[EditCommand, ...] = ()

    # ------------------------------------------------------------- consultas

    @property
    def history(self) -> EditHistory:
        return self._history

    @property
    def objects(self) -> tuple[EditObject, ...]:
        return tuple(self._objects.values())

    @property
    def can_undo(self) -> bool:
        return self._history.can_undo

    @property
    def can_redo(self) -> bool:
        return self._history.can_redo

    @property
    def is_dirty(self) -> bool:
        """Hay cambios activos distintos del último estado exportado.

        Se comparan las tuplas de comandos activos, no solo su cantidad: tras
        deshacer y añadir otro comando el número puede coincidir y el
        documento seguir siendo distinto del exportado.
        """
        return self._history.active_commands != self._saved_commands

    def mark_saved(self) -> None:
        """Registra el estado actual como exportado."""
        self._saved_commands = self._history.active_commands

    @property
    def active_command_count(self) -> int:
        return self._history.index

    def object(self, object_id: str) -> EditObject | None:
        return self._objects.get(object_id)

    def objects_on_page(self, page_index: int) -> tuple[EditObject, ...]:
        return tuple(obj for obj in self._objects.values() if obj.page_index == page_index)

    # ------------------------------------------------------------- acciones

    def add_text(
        self,
        page_index: int,
        rect: PdfRect,
        text: str,
        style: TextStyle | None = None,
    ) -> TextObject:
        obj = TextObject(
            object_id=self._new_id("texto"),
            page_index=page_index,
            rect=rect,
            text=text,
            style=style if style is not None else TextStyle(),
        )
        self._push(AddTextCommand(obj))
        return obj

    def add_image(
        self,
        page_index: int,
        rect: PdfRect,
        data: bytes,
        mime_type: str,
        *,
        source_path: Path | None = None,
    ) -> ImageObject:
        obj = ImageObject(
            object_id=self._new_id("imagen"),
            page_index=page_index,
            rect=rect,
            data=data,
            mime_type=mime_type,
            source_path=source_path,
        )
        self._push(AddImageCommand(obj))
        return obj

    def add_redaction(self, page_index: int, rect: PdfRect) -> RedactionObject:
        obj = RedactionObject(
            object_id=self._new_id("redaccion"),
            page_index=page_index,
            rect=rect,
        )
        self._push(AddRedactionCommand(obj))
        return obj

    def move_object(self, object_id: str, rect: PdfRect) -> None:
        obj = self._require(object_id)
        self._push(MoveObjectCommand(object_id, obj.page_index, rect))

    def resize_object(self, object_id: str, rect: PdfRect) -> None:
        obj = self._require(object_id)
        self._push(ResizeObjectCommand(object_id, obj.page_index, rect))

    def delete_object(self, object_id: str) -> None:
        obj = self._require(object_id)
        self._push(DeleteObjectCommand(object_id, obj.page_index))

    def undo(self) -> bool:
        if self._history.undo() is None:
            return False
        self._rebuild()
        return True

    def redo(self) -> bool:
        if self._history.redo() is None:
            return False
        self._rebuild()
        return True

    def clear(self) -> None:
        self._history.clear()
        self._objects.clear()
        self._saved_commands = ()

    # ------------------------------------------------------------ internos

    def _default_id(self, prefix: str) -> str:
        count = self._counters.get(prefix, 0) + 1
        self._counters[prefix] = count
        return f"{prefix}-{count}"

    def _new_id(self, prefix: str) -> str:
        return self._id_factory(prefix)

    def _require(self, object_id: str) -> EditObject:
        obj = self._objects.get(object_id)
        if obj is None:
            raise EditObjectNotFoundError(object_id)
        return obj

    def _push(self, command: EditCommand) -> None:
        self._history.push(command)
        self._rebuild()

    def _rebuild(self) -> None:
        objects: dict[str, EditObject] = {}
        for command in self._history.active_commands:
            objects = apply_command(objects, command)
        self._objects = objects
