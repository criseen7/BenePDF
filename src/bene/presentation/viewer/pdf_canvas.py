"""Lienzo que pinta la página renderizada."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPaintEvent
from PySide6.QtWidgets import QWidget

from bene.application.ports.pdf_engine import RenderedPage

PLACEHOLDER_SIZE = QSize(640, 480)
BACKGROUND = QColor("#23272b")
MESSAGE_COLOR = QColor("#c9cdd1")
PLACEHOLDER_MESSAGE = "Abre un PDF para empezar"


def rendered_page_to_image(render: RenderedPage) -> QImage:
    """Convierte el DTO del puerto en un ``QImage`` que posee sus píxeles."""
    image = QImage(
        render.samples,
        render.width,
        render.height,
        render.stride,
        QImage.Format.Format_RGB888,
    )
    # QImage no copia el búfer de bytes: hay que duplicarlo para que no dependa
    # de la vida del objeto Python.
    return image.copy()


class PdfCanvas(QWidget):
    """Muestra una página a tamaño real; el desplazamiento lo aporta QScrollArea."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._image: QImage | None = None
        self._message = PLACEHOLDER_MESSAGE
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self.setFixedSize(PLACEHOLDER_SIZE)

    @property
    def image(self) -> QImage | None:
        return self._image

    @property
    def has_image(self) -> bool:
        return self._image is not None

    @property
    def message(self) -> str:
        return self._message

    def set_image(self, image: QImage | None) -> None:
        self._image = image
        self.setFixedSize(image.size() if image is not None else PLACEHOLDER_SIZE)
        self.update()

    def set_message(self, message: str) -> None:
        self._message = message
        self.update()

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
        painter.drawImage(0, 0, self._image)
