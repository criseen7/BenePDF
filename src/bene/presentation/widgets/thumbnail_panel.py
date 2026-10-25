"""Panel lateral de miniaturas para navegar por el documento."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon, QImage, QPixmap
from PySide6.QtWidgets import QListWidget, QListWidgetItem, QWidget

THUMBNAIL_ICON_SIZE = QSize(96, 128)
THUMBNAIL_ITEM_SIZE = QSize(124, 168)


class ThumbnailPanel(QListWidget):
    """Lista vertical de páginas; emite la página al hacer clic."""

    page_activated = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("panel_miniaturas")
        self.setIconSize(THUMBNAIL_ICON_SIZE)
        self.setViewMode(QListWidget.ViewMode.ListMode)
        self.setMovement(QListWidget.Movement.Static)
        self.setUniformItemSizes(True)
        self.setSpacing(4)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.itemClicked.connect(self._on_item_clicked)

    @property
    def page_count(self) -> int:
        return self.count()

    def set_page_count(self, count: int) -> None:
        self.clear()
        for index in range(max(0, count)):
            item = QListWidgetItem(str(index + 1))
            item.setData(Qt.ItemDataRole.UserRole, index)
            item.setSizeHint(THUMBNAIL_ITEM_SIZE)
            item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter)
            self.addItem(item)

    def set_thumbnail(self, page_index: int, image: QImage) -> None:
        item = self.item(page_index)
        if item is None or image.isNull():
            return
        pixmap = QPixmap.fromImage(image)
        scaled = pixmap.scaled(
            THUMBNAIL_ICON_SIZE,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        item.setIcon(QIcon(scaled))

    def thumbnail(self, page_index: int) -> QIcon:
        item = self.item(page_index)
        return item.icon() if item is not None else QIcon()

    def set_current_page(self, page_index: int) -> None:
        if not 0 <= page_index < self.count():
            return
        self.blockSignals(True)
        self.setCurrentRow(page_index)
        self.blockSignals(False)
        self.scrollToItem(self.item(page_index))

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        index = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(index, int):
            self.page_activated.emit(index)
