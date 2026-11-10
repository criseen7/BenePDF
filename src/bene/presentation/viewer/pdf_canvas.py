"""Lienzo que pinta la página renderizada y los objetos de edición.

La página se dibuja como imagen de fondo y los objetos añadidos se superponen
con ``QPainter`` (ADR-002). El lienzo no modifica el PDF: solo comunica las
regiones, selecciones y transformaciones que el usuario solicita.
"""

from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum
from typing import Final

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QImage,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
)
from PySide6.QtWidgets import QWidget

from bene.application.ports.pdf_engine import RenderedPage
from bene.domain.editing import (
    EditObject,
    ImageObject,
    ImageReplacementObject,
    RedactionObject,
    TextAlignment,
    TextObject,
)
from bene.domain.models import PdfRect
from bene.presentation.fonts import qt_font_family
from bene.presentation.viewer.coordinates import CoordinateMapper

PLACEHOLDER_SIZE = QSize(640, 480)
BACKGROUND = QColor("#23272b")
MESSAGE_COLOR = QColor("#c9cdd1")
PLACEHOLDER_MESSAGE = "Abre un PDF para empezar"

SELECTION_COLOR = QColor("#3daee9")
REGION_COLOR = QColor(61, 174, 233, 55)
REDACTION_COLOR = QColor(16, 16, 16, 200)
REDACTION_BORDER = QColor("#e5534b")
REPLACEMENT_BORDER = QColor("#2f9e44")
SEARCH_COLOR = QColor(255, 214, 0, 70)
SEARCH_CURRENT_BORDER = QColor("#ff9f1a")
OVERFLOW_COLOR = QColor("#e5534b")
HANDLE_COLOR = QColor("#ffffff")
HANDLE_SIZE: Final[int] = 10
# Poco más que el asa dibujada: si el radio es grande, arrastrar el cuerpo
# cerca de una esquina se confunde con un redimensionado.
HANDLE_HIT_RADIUS: Final[float] = 7.0
MIN_OBJECT_SIZE: Final[float] = 4.0
MIN_REGION_PIXELS: Final[float] = 3.0


def rendered_page_to_image(render: RenderedPage, *, pixel_ratio: float = 1.0) -> QImage:
    """Convierte el DTO del puerto en un ``QImage`` que posee sus píxeles.

    ``pixel_ratio`` es la densidad de la pantalla: si el render se pidió a esa
    densidad, marcarla en la imagen hace que Qt la dibuje a su tamaño lógico sin
    perder nitidez en pantallas HiDPI.
    """
    image = QImage(
        render.samples,
        render.width,
        render.height,
        render.stride,
        QImage.Format.Format_RGB888,
    )
    # QImage no copia el búfer de bytes: hay que duplicarlo para que no dependa
    # de la vida del objeto Python.
    copied = image.copy()
    if pixel_ratio > 0:
        copied.setDevicePixelRatio(pixel_ratio)
    return copied


class CanvasTool(StrEnum):
    """Herramienta activa del lienzo."""

    SELECT = "select"
    REGION = "region"
    REDACT = "redact"
    PLACE = "place"


class PdfCanvas(QWidget):
    """Muestra una página y permite seleccionar y transformar objetos."""

    region_selected = Signal(object)  # PdfRect
    redaction_requested = Signal(object)  # PdfRect
    selection_changed = Signal(object)  # str | None
    transform_requested = Signal(str, object)  # (object_id, PdfRect)
    placement_requested = Signal(float, float)  # (page_x, page_y)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._image: QImage | None = None
        self._message = PLACEHOLDER_MESSAGE
        self._mapper: CoordinateMapper | None = None
        self._objects: tuple[EditObject, ...] = ()
        self._selected_id: str | None = None
        self._tool = CanvasTool.SELECT
        self._region: PdfRect | None = None
        self._region_view: QRectF | None = None
        self._image_cache: dict[str, QImage] = {}
        self._overflow_ids: set[str] = set()
        self._search_rects: tuple[PdfRect, ...] = ()
        self._search_current: PdfRect | None = None

        self._drag_mode: str | None = None
        self._drag_origin = QPointF()
        self._drag_start_page = (0.0, 0.0)
        self._drag_object_id: str | None = None
        self._drag_original_rect: PdfRect | None = None
        self._drag_preview_rect: PdfRect | None = None
        self._resize_corner: int | None = None

        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self.setFixedSize(PLACEHOLDER_SIZE)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName("Página del documento")
        self.setAccessibleDescription(PLACEHOLDER_MESSAGE)

    # ------------------------------------------------------------- propiedades

    @property
    def image(self) -> QImage | None:
        return self._image

    @property
    def has_image(self) -> bool:
        return self._image is not None

    @property
    def message(self) -> str:
        return self._message

    @property
    def mapper(self) -> CoordinateMapper | None:
        return self._mapper

    @property
    def objects(self) -> tuple[EditObject, ...]:
        return self._objects

    @property
    def selected_object_id(self) -> str | None:
        return self._selected_id

    @property
    def region(self) -> PdfRect | None:
        return self._region

    @property
    def tool(self) -> CanvasTool:
        return self._tool

    @property
    def overflow_ids(self) -> frozenset[str]:
        return frozenset(self._overflow_ids)

    @property
    def search_highlights(self) -> tuple[PdfRect, ...]:
        return self._search_rects

    @property
    def current_search_highlight(self) -> PdfRect | None:
        return self._search_current

    # ---------------------------------------------------------------- estado

    def set_image(self, image: QImage | None) -> None:
        self._image = image
        if image is None:
            self.setFixedSize(PLACEHOLDER_SIZE)
        else:
            ratio = image.devicePixelRatio() or 1.0
            self.setFixedSize(
                QSize(
                    max(1, round(image.width() / ratio)),
                    max(1, round(image.height() / ratio)),
                )
            )
        self.update()

    def set_message(self, message: str) -> None:
        self._message = message
        self.setAccessibleDescription(message)
        self.update()

    def set_mapper(self, mapper: CoordinateMapper | None) -> None:
        self._mapper = mapper
        self.update()

    def set_objects(self, objects: Iterable[EditObject]) -> None:
        previous = {obj.object_id: obj for obj in self._objects}
        self._objects = tuple(objects)
        current_ids = {obj.object_id for obj in self._objects}
        for object_id, obj in previous.items():
            if object_id in current_ids and previous[object_id] != obj:
                self._image_cache.pop(object_id, None)
        self._image_cache = {
            key: value for key, value in self._image_cache.items() if key in current_ids
        }

        if self._selected_id is not None and self._selected_id not in current_ids:
            self._selected_id = None
            self.selection_changed.emit(None)
        self.update()

    def set_tool(self, tool: CanvasTool) -> None:
        self._tool = tool
        if tool is CanvasTool.SELECT:
            self.unsetCursor()
        else:
            self.setCursor(Qt.CursorShape.CrossCursor)
        self.update()

    def set_overflow_ids(self, object_ids: Iterable[str]) -> None:
        """Marca los textos que no caben en su región con un borde de aviso."""
        overflow = set(object_ids)
        if overflow != self._overflow_ids:
            self._overflow_ids = overflow
            self.update()

    def set_region(self, region: PdfRect | None) -> None:
        self._region = region
        self._region_view = None
        self.update()

    def clear_region(self) -> None:
        self.set_region(None)

    def set_search_highlights(
        self,
        rects: Iterable[PdfRect],
        current: PdfRect | None = None,
    ) -> None:
        """Resalta las coincidencias de búsqueda de la página actual."""
        highlights = tuple(rects)
        if highlights == self._search_rects and current == self._search_current:
            return
        self._search_rects = highlights
        self._search_current = current
        self.update()

    def clear_search_highlights(self) -> None:
        self.set_search_highlights((), None)

    def select_object(self, object_id: str | None) -> None:
        if object_id is not None and not any(obj.object_id == object_id for obj in self._objects):
            object_id = None
        if object_id == self._selected_id:
            return
        self._selected_id = object_id
        self.update()
        self.selection_changed.emit(object_id)

    # ---------------------------------------------------------------- pintura

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), BACKGROUND)
        if self._image is None:
            painter.setPen(MESSAGE_COLOR)
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                self._message,
            )
            return

        # Las imágenes insertadas se dibujan escaladas; suavizarlas mantiene la
        # calidad de la vista previa.
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.drawImage(0, 0, self._image)
        if self._mapper is None:
            return

        for obj in self._objects:
            self._paint_object(painter, obj)
        self._paint_search(painter)
        self._paint_region(painter)
        self._paint_selection(painter)

    def _paint_search(self, painter: QPainter) -> None:
        mapper = self._mapper
        if mapper is None or not self._search_rects:
            return
        painter.setBrush(SEARCH_COLOR)
        painter.setPen(Qt.PenStyle.NoPen)
        for rect in self._search_rects:
            painter.drawRect(QRectF(*mapper.rect_to_view(rect)))
        if self._search_current is not None:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(SEARCH_CURRENT_BORDER, 2))
            painter.drawRect(QRectF(*mapper.rect_to_view(self._search_current)))

    def _paint_object(self, painter: QPainter, obj: EditObject) -> None:
        mapper = self._mapper
        if mapper is None:
            return
        rect = self._display_rect(obj)
        view_rect = QRectF(*mapper.rect_to_view(rect))

        if isinstance(obj, TextObject):
            self._paint_text(painter, obj, view_rect)
            if obj.object_id in self._overflow_ids:
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.setPen(QPen(OVERFLOW_COLOR, 1, Qt.PenStyle.DashLine))
                painter.drawRect(view_rect)
        elif isinstance(obj, ImageObject):
            image = self._image_for(obj)
            if image.isNull():
                painter.fillRect(view_rect, QColor(180, 60, 60, 80))
                painter.setPen(QColor("#ffffff"))
                painter.drawText(
                    view_rect,
                    Qt.AlignmentFlag.AlignCenter,
                    "Imagen no válida",
                )
            else:
                painter.drawImage(view_rect, image)
        elif isinstance(obj, ImageReplacementObject):
            image = self._image_for(obj)
            if image.isNull():
                painter.fillRect(view_rect, QColor(180, 60, 60, 80))
            else:
                painter.drawImage(view_rect, image)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(REPLACEMENT_BORDER, 1, Qt.PenStyle.DashLine))
            painter.drawRect(view_rect)
        elif isinstance(obj, RedactionObject):
            self._paint_redaction(painter, view_rect)

    @staticmethod
    def _paint_redaction(painter: QPainter, view_rect: QRectF) -> None:
        painter.fillRect(view_rect, REDACTION_COLOR)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(REDACTION_BORDER, 1, Qt.PenStyle.DashLine))
        painter.drawRect(view_rect)

    def _paint_text(self, painter: QPainter, obj: TextObject, view_rect: QRectF) -> None:
        mapper = self._mapper
        assert mapper is not None
        font = QFont(qt_font_family(obj.style.font_name))
        font.setPixelSize(max(1, round(obj.style.font_size * mapper.scale)))
        painter.setFont(font)
        painter.setPen(QColor(obj.style.color))
        horizontal = {
            TextAlignment.LEFT: Qt.AlignmentFlag.AlignLeft,
            TextAlignment.CENTER: Qt.AlignmentFlag.AlignHCenter,
            TextAlignment.RIGHT: Qt.AlignmentFlag.AlignRight,
        }[obj.style.alignment]
        flags = int(horizontal | Qt.AlignmentFlag.AlignTop) | int(Qt.TextFlag.TextWordWrap)
        painter.drawText(view_rect, flags, obj.text)

    def _paint_region(self, painter: QPainter) -> None:
        if self._region_view is not None:
            view_rect = self._region_view
        elif self._region is not None and self._mapper is not None:
            view_rect = QRectF(*self._mapper.rect_to_view(self._region))
        else:
            return

        painter.setBrush(REGION_COLOR)
        painter.setPen(QPen(SELECTION_COLOR, 1, Qt.PenStyle.DashLine))
        painter.drawRect(view_rect)

    def _paint_selection(self, painter: QPainter) -> None:
        obj = self._selected_object()
        if obj is None or self._mapper is None:
            return

        rect = self._display_rect(obj)
        view_rect = QRectF(*self._mapper.rect_to_view(rect))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(SELECTION_COLOR, 1, Qt.PenStyle.DashLine))
        painter.drawRect(view_rect)

        painter.setBrush(HANDLE_COLOR)
        painter.setPen(QPen(SELECTION_COLOR, 1))
        for corner in self._page_corners(rect):
            x, y = self._mapper.to_view(*corner)
            painter.drawRect(
                QRectF(
                    x - HANDLE_SIZE / 2,
                    y - HANDLE_SIZE / 2,
                    HANDLE_SIZE,
                    HANDLE_SIZE,
                )
            )

    # --------------------------------------------------------------- eventos

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton or self._mapper is None:
            return

        position = event.position()
        if self._tool in (CanvasTool.REGION, CanvasTool.REDACT):
            self._drag_mode = "redact" if self._tool is CanvasTool.REDACT else "region"
            self._drag_origin = position
            self._region_view = QRectF(position, position)
            self.update()
            return

        if self._tool is CanvasTool.PLACE:
            page_x, page_y = self._mapper.to_page_clamped(position.x(), position.y())
            self.placement_requested.emit(page_x, page_y)
            return

        target = self._handle_at(position)
        if target is not None:
            obj = self._selected_object()
            assert obj is not None
            self._drag_mode = "resize"
            self._resize_corner = target
            self._drag_object_id = obj.object_id
            self._drag_original_rect = obj.rect
            self._drag_preview_rect = obj.rect
            return

        obj = self._object_at(position)
        if obj is None:
            self.select_object(None)
            return

        self.select_object(obj.object_id)
        self._drag_mode = "move"
        self._drag_origin = position
        self._drag_start_page = self._mapper.to_page(position.x(), position.y())
        self._drag_object_id = obj.object_id
        self._drag_original_rect = obj.rect
        self._drag_preview_rect = obj.rect

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._mapper is None:
            return
        position = event.position()

        if self._drag_mode is None and self._tool is CanvasTool.SELECT:
            self._update_hover_cursor(position)
            return

        if self._drag_mode in ("region", "redact") and self._region_view is not None:
            self._region_view = QRectF(self._drag_origin, position).normalized()
            self.update()
            return

        if self._drag_mode == "move" and self._drag_original_rect is not None:
            current = self._mapper.to_page(position.x(), position.y())
            dx = current[0] - self._drag_start_page[0]
            dy = current[1] - self._drag_start_page[1]
            self._drag_preview_rect = self._clamped_translation(self._drag_original_rect, dx, dy)
            self.update()
            return

        if (
            self._drag_mode == "resize"
            and self._drag_original_rect is not None
            and self._resize_corner is not None
        ):
            point = self._mapper.to_page_clamped(position.x(), position.y())
            preserve_aspect = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            self._drag_preview_rect = self._resized_rect(
                self._drag_original_rect,
                self._resize_corner,
                point,
                preserve_aspect=preserve_aspect,
            )
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return

        if self._drag_mode in ("region", "redact"):
            self._finish_region()
        elif self._drag_mode in ("move", "resize"):
            self._finish_transform()

        self._drag_mode = None
        self._resize_corner = None
        self._drag_object_id = None
        self._drag_original_rect = None
        self._drag_preview_rect = None
        self.update()

    # -------------------------------------------------------------- internos

    def _finish_region(self) -> None:
        if self._mapper is None or self._region_view is None:
            return
        view = self._region_view
        is_redaction = self._drag_mode == "redact"
        if view.width() < MIN_REGION_PIXELS or view.height() < MIN_REGION_PIXELS:
            self._region = None
        else:
            self._region = self._mapper.rect_to_page(
                view.left(), view.top(), view.right(), view.bottom()
            )
            if is_redaction:
                self.redaction_requested.emit(self._region)
                self._region = None
            else:
                self.region_selected.emit(self._region)
        self._region_view = None

    def _finish_transform(self) -> None:
        if (
            self._drag_object_id is None
            or self._drag_preview_rect is None
            or self._drag_original_rect is None
        ):
            return
        if self._drag_preview_rect != self._drag_original_rect:
            self.transform_requested.emit(self._drag_object_id, self._drag_preview_rect)

    def _selected_object(self) -> EditObject | None:
        if self._selected_id is None:
            return None
        return next((obj for obj in self._objects if obj.object_id == self._selected_id), None)

    def _display_rect(self, obj: EditObject) -> PdfRect:
        if obj.object_id == self._selected_id and self._drag_preview_rect is not None:
            return self._drag_preview_rect
        return obj.rect

    def _object_at(self, position: QPointF) -> EditObject | None:
        if self._mapper is None:
            return None
        for obj in reversed(self._objects):
            if QRectF(*self._mapper.rect_to_view(obj.rect)).contains(position):
                return obj
        return None

    def _handle_at_object(self, obj: EditObject, position: QPointF) -> int | None:
        if self._mapper is None:
            return None
        for index, corner in enumerate(self._page_corners(self._display_rect(obj))):
            x, y = self._mapper.to_view(*corner)
            if (
                abs(position.x() - x) <= HANDLE_HIT_RADIUS
                and abs(position.y() - y) <= HANDLE_HIT_RADIUS
            ):
                return index
        return None

    def _handle_at(self, position: QPointF) -> int | None:
        """Asa de la selección bajo el puntero, si la hay.

        Solo las asas visibles del objeto seleccionado son interactivas: así
        arrastrar el cuerpo nunca redimensiona por accidente.
        """
        obj = self._selected_object()
        if obj is None:
            return None
        return self._handle_at_object(obj, position)

    def _update_hover_cursor(self, position: QPointF) -> None:
        corner = self._handle_at(position)
        if corner is not None:
            # Las esquinas 0 y 2 son la diagonal principal; 1 y 3, la inversa.
            self.setCursor(
                Qt.CursorShape.SizeFDiagCursor
                if corner in (0, 2)
                else Qt.CursorShape.SizeBDiagCursor
            )
        elif self._object_at(position) is not None:
            self.setCursor(Qt.CursorShape.SizeAllCursor)
        else:
            self.unsetCursor()

    @staticmethod
    def _page_corners(rect: PdfRect) -> tuple[tuple[float, float], ...]:
        return (
            (rect.x0, rect.y0),
            (rect.x1, rect.y0),
            (rect.x1, rect.y1),
            (rect.x0, rect.y1),
        )

    def _clamped_translation(self, rect: PdfRect, dx: float, dy: float) -> PdfRect:
        assert self._mapper is not None
        dx = max(-rect.x0, min(dx, self._mapper.page_width - rect.x1))
        dy = max(-rect.y0, min(dy, self._mapper.page_height - rect.y1))
        return rect.translated(dx, dy)

    def _resized_rect(
        self,
        rect: PdfRect,
        corner: int,
        point: tuple[float, float],
        *,
        preserve_aspect: bool = False,
    ) -> PdfRect:
        left = corner in (0, 3)
        top = corner in (0, 1)
        x, y = point

        if left:
            x0 = min(x, rect.x1 - MIN_OBJECT_SIZE)
            x1 = rect.x1
        else:
            x0 = rect.x0
            x1 = max(x, rect.x0 + MIN_OBJECT_SIZE)
        if top:
            y0 = min(y, rect.y1 - MIN_OBJECT_SIZE)
            y1 = rect.y1
        else:
            y0 = rect.y0
            y1 = max(y, rect.y0 + MIN_OBJECT_SIZE)

        if preserve_aspect and rect.width > 0 and rect.height > 0:
            ratio = rect.width / rect.height
            width = x1 - x0
            height = y1 - y0
            # Manda el eje que más crece, para que el objeto no se encoja
            # cuando el puntero apenas se mueve en el otro eje.
            if width / rect.width >= height / rect.height:
                height = width / ratio
            else:
                width = height * ratio

            if self._mapper is not None:
                max_width = x1 if left else self._mapper.page_width - x0
                max_height = y1 if top else self._mapper.page_height - y0
                scale = min(1.0, max_width / width, max_height / height)
                width *= scale
                height *= scale

            if left:
                x0 = x1 - width
            else:
                x1 = x0 + width
            if top:
                y0 = y1 - height
            else:
                y1 = y0 + height

        return PdfRect(x0, y0, x1, y1)

    def _image_for(self, obj: ImageObject | ImageReplacementObject) -> QImage:
        cached = self._image_cache.get(obj.object_id)
        if cached is not None:
            return cached
        image = QImage.fromData(obj.data)
        self._image_cache[obj.object_id] = image
        return image
