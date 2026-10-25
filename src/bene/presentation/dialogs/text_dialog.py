"""Diálogo para crear un cuadro de texto (RF-007)."""

from __future__ import annotations

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from bene.domain.editing import SUPPORTED_FONTS, TextAlignment, TextStyle


class TextDialog(QDialog):
    """Pide contenido y estilo; el llamador decide dónde colocarlo."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        text: str = "",
        style: TextStyle | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Añadir texto")
        self.setModal(True)
        self.resize(520, 420)
        current = style if style is not None else TextStyle()

        self._text = QPlainTextEdit(self)
        self._text.setPlaceholderText("Escribe el texto que quieres añadir…")
        self._text.setPlainText(text)
        self._text.textChanged.connect(self._update_ok)

        self._font = QComboBox(self)
        self._font.addItems(SUPPORTED_FONTS)
        index = self._font.findText(current.font_name)
        if index >= 0:
            self._font.setCurrentIndex(index)

        self._size = QDoubleSpinBox(self)
        self._size.setRange(6.0, 200.0)
        self._size.setDecimals(1)
        self._size.setSingleStep(1.0)
        self._size.setSuffix(" pt")
        self._size.setValue(current.font_size)

        self._color = QColor(current.color)
        self._color_button = QPushButton(self)
        self._color_button.clicked.connect(self._choose_color)
        self._update_color_button()

        self._alignment = QComboBox(self)
        self._alignment.addItem("Izquierda", TextAlignment.LEFT)
        self._alignment.addItem("Centro", TextAlignment.CENTER)
        self._alignment.addItem("Derecha", TextAlignment.RIGHT)
        alignment_index = self._alignment.findData(current.alignment)
        if alignment_index >= 0:
            self._alignment.setCurrentIndex(alignment_index)

        form = QFormLayout()
        form.addRow("Fuente:", self._font)
        form.addRow("Tamaño:", self._size)
        form.addRow("Color:", self._color_button)
        form.addRow("Alineación:", self._alignment)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Texto:", self))
        layout.addWidget(self._text, 1)
        layout.addLayout(form)
        layout.addWidget(self._buttons)

        self._update_ok()

    @property
    def text(self) -> str:
        return self._text.toPlainText()

    @property
    def chosen_style(self) -> TextStyle:
        data = self._alignment.currentData()
        try:
            alignment = TextAlignment(data)
        except ValueError:
            alignment = TextAlignment.LEFT
        return TextStyle(
            font_name=self._font.currentText(),
            font_size=self._size.value(),
            color=self._color.name(),
            alignment=alignment,
        )

    def accept(self) -> None:
        if not self.text.strip():
            return
        super().accept()

    def _update_ok(self) -> None:
        button = self._buttons.button(QDialogButtonBox.StandardButton.Ok)
        if button is not None:
            button.setEnabled(bool(self.text.strip()))

    def _choose_color(self) -> None:
        color = QColorDialog.getColor(self._color, self, "Color del texto")
        if color.isValid():
            self._color = color
            self._update_color_button()

    def _update_color_button(self) -> None:
        contrast = "#000000" if self._color.lightness() > 128 else "#ffffff"
        self._color_button.setText(self._color.name())
        self._color_button.setStyleSheet(
            f"background-color: {self._color.name()}; color: {contrast};"
        )
