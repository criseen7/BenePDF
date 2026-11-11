"""Sesión de edición con historial de comandos (ADR-002, RF-014).

La sesión mantiene la lista completa de comandos y un índice que separa los
activos de los que se pueden rehacer. El estado visible se reconstruye
aplicando solo los comandos activos, así que deshacer y rehacer no puede dejar
el documento en un estado intermedio inconsistente.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path

from bene.domain.editing import (
    PAGE_COMMANDS,
    AddImageCommand,
    AddImageReplacementCommand,
    AddRedactionCommand,
    AddStrokeCommand,
    AddTextCommand,
    DeleteObjectCommand,
    DeletePageCommand,
    EditCommand,
    EditObject,
    ImageObject,
    ImageReplacementObject,
    MoveObjectCommand,
    MovePageCommand,
    RedactionObject,
    ResizeObjectCommand,
    RotatePageCommand,
    StrokeObject,
    StrokeStyle,
    TextObject,
    TextStyle,
    apply_command,
    apply_page_command,
)
from bene.domain.errors import (
    EditObjectNotFoundError,
    InvalidEditOperationError,
    PageOutOfRangeError,
)
from bene.domain.models import PdfRect
from bene.domain.pages import PageArrangement

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

    def __init__(self, *, id_factory: IdFactory | None = None, page_count: int = 0) -> None:
        if page_count < 0:
            raise ValueError(f"El número de páginas no puede ser negativo: {page_count}")
        self._history = EditHistory()
        self._objects: dict[str, EditObject] = {}
        self._id_factory = id_factory or self._default_id
        self._counters: dict[str, int] = {}
        self._saved_commands: tuple[EditCommand, ...] = ()
        self._page_count = page_count
        self._arrangement = PageArrangement.initial(page_count)

    # ------------------------------------------------------------- consultas

    @property
    def history(self) -> EditHistory:
        return self._history

    @property
    def page_count(self) -> int:
        """Páginas del documento fuente."""
        return self._page_count

    @property
    def page_arrangement(self) -> PageArrangement:
        return self._arrangement

    @property
    def output_page_count(self) -> int:
        return self._arrangement.output_page_count

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
        self._require_page_for_object(page_index)
        obj = TextObject(
            object_id=self._new_id("texto"),
            page_index=page_index,
            rect=rect,
            text=text,
            style=style if style is not None else TextStyle(),
        )
        self._push(AddTextCommand(obj))
        return obj

    def add_stroke(
        self,
        page_index: int,
        points: Iterable[tuple[float, float]],
        style: StrokeStyle | None = None,
    ) -> StrokeObject:
        self._require_page_for_object(page_index)
        obj = StrokeObject(
            object_id=self._new_id("trazo"),
            page_index=page_index,
            points=tuple(points),
            style=style if style is not None else StrokeStyle(),
        )
        self._push(AddStrokeCommand(obj))
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
        self._require_page_for_object(page_index)
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
        self._require_page_for_object(page_index)
        obj = RedactionObject(
            object_id=self._new_id("redaccion"),
            page_index=page_index,
            rect=rect,
        )
        self._push(AddRedactionCommand(obj))
        return obj

    def replace_image(
        self,
        page_index: int,
        image_id: str,
        rect: PdfRect,
        data: bytes,
        mime_type: str,
        *,
        source_path: Path | None = None,
    ) -> ImageReplacementObject:
        self._require_page_for_object(page_index)
        obj = ImageReplacementObject(
            object_id=self._new_id("reemplazo"),
            page_index=page_index,
            image_id=image_id,
            rect=rect,
            data=data,
            mime_type=mime_type,
            source_path=source_path,
        )
        self._push(AddImageReplacementCommand(obj))
        return obj

    def move_object(self, object_id: str, rect: PdfRect) -> None:
        obj = self._require(object_id)
        self._require_page_for_object(obj.page_index)
        self._push(MoveObjectCommand(object_id, obj.page_index, rect))

    def resize_object(self, object_id: str, rect: PdfRect) -> None:
        obj = self._require(object_id)
        self._require_page_for_object(obj.page_index)
        self._push(ResizeObjectCommand(object_id, obj.page_index, rect))

    def delete_object(self, object_id: str) -> None:
        obj = self._require(object_id)
        self._push(DeleteObjectCommand(object_id, obj.page_index))

    # ------------------------------------------------------------- páginas

    def rotate_page(self, page_index: int, degrees: int = 90) -> None:
        """Acumula una rotación adicional a una página fuente."""
        self._require_page(page_index)
        self._push(RotatePageCommand(page_index, degrees))

    def move_page(self, from_position: int, to_position: int) -> None:
        """Mueve una página entre posiciones de la disposición actual."""
        self._require_position(from_position)
        self._require_position(to_position)
        self._push(MovePageCommand(from_position, to_position))

    def delete_page(self, page_index: int) -> None:
        """Elimina una página fuente de la copia de trabajo."""
        self._require_page(page_index)
        if self._arrangement.output_page_count <= 1:
            raise InvalidEditOperationError("No se puede eliminar la última página del documento")
        self._push(DeletePageCommand(page_index))

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
        self._arrangement = PageArrangement.initial(self._page_count)
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

    def _require_page(self, page_index: int) -> None:
        if not 0 <= page_index < self._page_count:
            raise PageOutOfRangeError(page_index, self._page_count)
        if not self._arrangement.is_present(page_index):
            raise InvalidEditOperationError(
                f"La página {page_index + 1} está eliminada de la copia de trabajo"
            )

    def _require_page_for_object(self, page_index: int) -> None:
        """Comprueba que la página existe en la copia de trabajo.

        Las sesiones sin ``page_count`` (pruebas de objetos aislados) no validan
        el índice; cuando la ventana abre un documento siempre se conoce.
        """
        if self._page_count > 0:
            self._require_page(page_index)

    def _require_position(self, position: int) -> None:
        if not 0 <= position < self._arrangement.output_page_count:
            raise PageOutOfRangeError(position, self._arrangement.output_page_count)

    def _push(self, command: EditCommand) -> None:
        self._history.push(command)
        self._rebuild()

    def _rebuild(self) -> None:
        objects: dict[str, EditObject] = {}
        arrangement = PageArrangement.initial(self._page_count)
        for command in self._history.active_commands:
            if isinstance(command, PAGE_COMMANDS):
                arrangement = apply_page_command(arrangement, command)
            else:
                objects = apply_command(objects, command)
        self._objects = objects
        self._arrangement = arrangement
