"""Panel numérico de posición y tamaño del objeto seleccionado (RF-008)."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from bene.domain.editing import EditObject, ImageObject, RedactionObject, StrokeObject, TextObject
from bene.domain.models import PdfRect

MAX_COORDINATE: float = 100_000.0


class ObjectPropertiesPanel(QWidget):
    """Muestra y edita la geometría del objeto seleccionado en puntos PDF."""

    geometry_applied = Signal(float, float, float, float)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._object: EditObject | None = None
        self.setAccessibleName("Propiedades del objeto")

        self._title = QLabel("Sin selección", self)
        self._title.setAccessibleName("Objeto seleccionado")
        self._title.setStyleSheet("font-weight: bold;")
        self._hint = QLabel("Posición y tamaño en puntos PDF.", self)
        self._hint.setWordWrap(True)
        self._hint.setStyleSheet("color: #6c757d;")

        self._x = self._coordinate_spin()
        self._y = self._coordinate_spin()
        self._width = self._size_spin()
        self._height = self._size_spin()
        self._x.setAccessibleName("Coordenada X")
        self._y.setAccessibleName("Coordenada Y")
        self._width.setAccessibleName("Ancho")
        self._height.setAccessibleName("Alto")

        form = QFormLayout()
        form.addRow("X:", self._x)
        form.addRow("Y:", self._y)
        form.addRow("Ancho:", self._width)
        form.addRow("Alto:", self._height)

        self._preview = QLabel("", self)
        self._preview.setWordWrap(True)
        self._preview.setStyleSheet("color: #343a40;")

        self._apply = QPushButton("Aplicar cambios", self)
        self._apply.setAccessibleName("Aplicar cambios")
        self._apply.clicked.connect(self._emit_geometry)

        QWidget.setTabOrder(self._x, self._y)
        QWidget.setTabOrder(self._y, self._width)
        QWidget.setTabOrder(self._width, self._height)
        QWidget.setTabOrder(self._height, self._apply)

        layout = QVBoxLayout(self)
        layout.addWidget(self._title)
        layout.addWidget(self._hint)
        layout.addLayout(form)
        layout.addWidget(self._preview)
        layout.addWidget(self._apply)
        layout.addStretch(1)

        self.set_object(None)

    @property
    def object(self) -> EditObject | None:
        return self._object

    def set_object(self, obj: EditObject | None) -> None:
        self._object = obj
        enabled = obj is not None
        for widget in (self._x, self._y, self._width, self._height, self._apply):
            widget.setEnabled(enabled)

        if obj is None:
            self._title.setText("Sin selección")
            self._preview.setText("")
            self._preview.setVisible(False)
            self.set_geometry(PdfRect(0, 0, 1, 1))
            return

        if isinstance(obj, TextObject):
            self._title.setText("Texto añadido")
            self._preview.setText(obj.text)
            self._preview.setVisible(True)
        elif isinstance(obj, StrokeObject):
            self._title.setText("Trazo")
            self._preview.setText(
                f"Color {obj.style.color} · grosor {obj.style.width:g} pt · "
                f"{len(obj.points)} punto{'s' if len(obj.points) != 1 else ''}"
            )
            self._preview.setVisible(True)
        elif isinstance(obj, ImageObject):
            self._title.setText("Imagen añadida")
            self._preview.setText(f"Archivo: {obj.source_path.name}" if obj.source_path else "")
            self._preview.setVisible(bool(self._preview.text()))
        elif isinstance(obj, RedactionObject):
            self._title.setText("Redacción")
            self._preview.setText(
                "El contenido de esta región se eliminará de forma permanente al exportar."
            )
            self._preview.setVisible(True)
        self.set_geometry(obj.rect)

    def set_geometry(self, rect: PdfRect) -> None:
        self._x.setValue(rect.x0)
        self._y.setValue(rect.y0)
        self._width.setValue(max(rect.width, self._width.minimum()))
        self._height.setValue(max(rect.height, self._height.minimum()))

    def object_geometry(self) -> PdfRect:
        return PdfRect.from_size(
            self._width.value(),
            self._height.value(),
            x=self._x.value(),
            y=self._y.value(),
        )

    def _emit_geometry(self) -> None:
        rect = self.object_geometry()
        self.geometry_applied.emit(rect.x0, rect.y0, rect.width, rect.height)

    def _coordinate_spin(self) -> QDoubleSpinBox:
        spin = QDoubleSpinBox(self)
        spin.setRange(0.0, MAX_COORDINATE)
        spin.setDecimals(1)
        spin.setSingleStep(1.0)
        spin.setSuffix(" pt")
        return spin

    def _size_spin(self) -> QDoubleSpinBox:
        spin = self._coordinate_spin()
        spin.setRange(1.0, MAX_COORDINATE)
        return spin
