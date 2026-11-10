"""Diálogo para reemplazar una imagen ya incrustada (RF-013)."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from bene.application.ports.pdf_engine import EmbeddedImage
from bene.config import APP_NAME
from bene.presentation.images import ImageLoadError, LoadedImage, load_image


class ImageReplacementDialog(QDialog):
    """Lista las imágenes detectadas y pide el archivo de reemplazo."""

    def __init__(
        self,
        images: Sequence[EmbeddedImage],
        parent: QWidget | None = None,
        *,
        last_directory: Path | None = None,
    ) -> None:
        super().__init__(parent)
        self._images = tuple(images)
        self._replacement: LoadedImage | None = None
        self._last_directory = last_directory or Path.home()

        self.setWindowTitle("Reemplazar imagen")
        self.setAccessibleName("Reemplazar imagen incrustada")
        self.setAccessibleDescription(
            "Elige una imagen del documento y el archivo PNG o JPEG que la sustituirá."
        )
        self.setModal(True)
        self.resize(560, 480)

        self._list = QListWidget(self)
        self._list.setObjectName("lista_imagenes")
        self._list.setAccessibleName("Imágenes del documento")
        for index, image in enumerate(self._images):
            item = QListWidgetItem(_describe(image, index))
            item.setData(Qt.ItemDataRole.UserRole, index)
            self._list.addItem(item)
        self._list.currentRowChanged.connect(self._update_state)

        self._warning = QLabel("", self)
        self._warning.setObjectName("aviso_imagen_compartida")
        self._warning.setWordWrap(True)

        self._choose_button = QPushButton("Elegir imagen de reemplazo…", self)
        self._choose_button.setObjectName("boton_elegir_reemplazo")
        self._choose_button.clicked.connect(self._choose_file)

        self._preview = QLabel("Sin imagen de reemplazo", self)
        self._preview.setObjectName("vista_previa_reemplazo")
        self._preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview.setMinimumHeight(160)
        self._preview.setStyleSheet("QLabel { background: #f0f0f0; border: 1px solid #c0c0c0; }")

        self._buttons = QDialogButtonBox(self)
        self._accept_button = self._buttons.addButton(
            "Reemplazar", QDialogButtonBox.ButtonRole.AcceptRole
        )
        self._buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Imágenes detectadas en la página:", self))
        layout.addWidget(self._list, 1)
        layout.addWidget(self._warning)
        layout.addWidget(self._choose_button)
        layout.addWidget(self._preview, 1)
        layout.addWidget(self._buttons)

        if self._images:
            self._list.setCurrentRow(0)
        self._update_state()

    # ------------------------------------------------------------- propiedades

    @property
    def selected_image(self) -> EmbeddedImage | None:
        row = self._list.currentRow()
        if not 0 <= row < len(self._images):
            return None
        return self._images[row]

    @property
    def replacement(self) -> LoadedImage | None:
        return self._replacement

    @property
    def warning_text(self) -> str:
        return self._warning.text()

    # ----------------------------------------------------------------- estado

    def set_replacement(self, loaded: LoadedImage) -> None:
        """Fija la imagen de reemplazo sin abrir el selector de archivos."""
        self._replacement = loaded
        pixmap = QPixmap()
        pixmap.loadFromData(loaded.data)
        if pixmap.isNull():
            self._preview.setText("Vista previa no disponible")
        else:
            self._preview.setPixmap(
                pixmap.scaled(
                    480,
                    200,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        self._update_state()

    def _choose_file(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Imagen de reemplazo",
            str(self._last_directory),
            "Imágenes (*.png *.jpg *.jpeg)",
        )
        if not filename:
            return
        path = Path(filename)
        try:
            loaded = load_image(path)
        except ImageLoadError as error:
            QMessageBox.warning(self, APP_NAME, str(error))
            return
        self._last_directory = path.parent
        self.set_replacement(loaded)

    def _update_state(self) -> None:
        image = self.selected_image
        if image is not None and image.is_shared:
            pages = ", ".join(str(page + 1) for page in image.used_on_pages)
            self._warning.setText(
                "Esta imagen se comparte entre varias páginas "
                f"({pages}). Al reemplazarla cambiará en todas ellas."
            )
        else:
            self._warning.setText("")
        self._accept_button.setEnabled(image is not None and self._replacement is not None)


def _describe(image: EmbeddedImage, index: int) -> str:
    width = f"{image.pixel_width}×{image.pixel_height} px"
    area = f"{image.rect.width:.0f}×{image.rect.height:.0f} pt"
    shared = f" · compartida en {len(image.used_on_pages)} páginas" if image.is_shared else ""
    return f"Imagen {index + 1} · {width} · {area}{shared}"
