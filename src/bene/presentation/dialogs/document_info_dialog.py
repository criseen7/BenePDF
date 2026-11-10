"""Diálogo de información del documento (RF-022)."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from bene.domain.models import DocumentInfo

_METADATA_LABELS: tuple[tuple[str, str], ...] = (
    ("title", "Título"),
    ("author", "Autor"),
    ("subject", "Asunto"),
    ("keywords", "Palabras clave"),
    ("creator", "Creador"),
    ("producer", "Productor"),
    ("creationDate", "Fecha de creación"),
    ("modDate", "Última modificación"),
)


def format_file_size(size: int) -> str:
    """Tamaño legible en unidades binarias."""
    if size < 1024:
        return f"{size} B"
    value = float(size)
    for unit in ("KB", "MB", "GB", "TB"):
        value /= 1024.0
        if value < 1024.0 or unit == "TB":
            return f"{value:.1f} {unit}"
    return f"{size} B"


class DocumentInfoDialog(QDialog):
    """Muestra metadatos, tamaño y páginas del documento abierto."""

    def __init__(
        self,
        info: DocumentInfo,
        *,
        page_size: tuple[float, float] | None = None,
        output_page_count: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._info = info
        self._fields: dict[str, str] = {}

        self.setWindowTitle("Información del documento")
        self.setAccessibleName("Información del documento")
        self.setAccessibleDescription(
            "Metadatos, tamaño del archivo y número de páginas del PDF abierto."
        )
        self.setModal(True)
        self.resize(520, 460)

        form = QFormLayout()
        self._add_field(form, "Archivo", info.path.name)
        self._add_field(form, "Ruta", describe_path(info.path))
        self._add_field(form, "Páginas", str(info.page_count))
        if output_page_count is not None and output_page_count != info.page_count:
            self._add_field(
                form,
                "Páginas al exportar",
                f"{output_page_count} (se eliminarán {info.page_count - output_page_count})",
            )
        self._add_field(form, "Tamaño", format_file_size(info.file_size_bytes))
        if page_size is not None:
            width, height = page_size
            self._add_field(form, "Página actual", f"{width:.0f} × {height:.0f} pt")
        self._add_field(form, "Protección", "Cifrado" if info.encrypted else "Sin cifrado")

        metadata = info.metadata or {}
        for key, label in _METADATA_LABELS:
            value = _metadata_value(metadata, key)
            if value:
                self._add_field(form, label, value)

        note = QLabel(
            "Los datos proceden de los metadatos del PDF. Pueden faltar o ser "
            "incorrectos si el archivo no los declara.",
            self,
        )
        note.setWordWrap(True)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(note)
        layout.addStretch(1)
        layout.addWidget(buttons)

    @property
    def info(self) -> DocumentInfo:
        return self._info

    @property
    def fields(self) -> Mapping[str, str]:
        return dict(self._fields)

    def _add_field(self, form: QFormLayout, label: str, value: str) -> None:
        self._fields[label] = value
        value_label = QLabel(value, self)
        value_label.setWordWrap(True)
        value_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        form.addRow(f"{label}:", value_label)


def _metadata_value(metadata: Mapping[str, str], key: str) -> str:
    value = metadata.get(key, "")
    return value.strip() if isinstance(value, str) else ""


def describe_path(path: Path) -> str:
    """Ruta absoluta para mostrar en el diálogo."""
    try:
        return str(path.expanduser().absolute())
    except OSError:
        return str(path)
