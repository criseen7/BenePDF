"""Smoke real con PyMuPDF: miniaturas y edición en memoria (iteración 2).

Recorre el flujo completo de la ventana principal con el motor de verdad y
comprueba que el archivo original queda intacto y que no se escribe nada.
"""

from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest
from PySide6.QtCore import QBuffer, QByteArray, QIODevice
from PySide6.QtGui import QColor, QImage, QImageWriter
from PySide6.QtWidgets import QMessageBox
from pytestqt.qtbot import QtBot

from bene.application.use_cases.open_document import OpenDocument
from bene.application.use_cases.render_page import RenderPage
from bene.domain.editing import EditObject, ImageObject, RedactionObject, TextObject, TextStyle
from bene.domain.models import PdfRect
from bene.infrastructure.pdf.pymupdf_engine import PyMuPDFEngine
from bene.presentation.main_window import MainWindow
from bene.presentation.widgets.thumbnail_panel import ThumbnailPanel
from tests.integration import synthetic

pytestmark = pytest.mark.ui

TIMEOUT_MS = 15_000


def session_objects(window: MainWindow) -> tuple[EditObject, ...]:
    session = window.edit_session
    assert session is not None
    return session.objects


def png_bytes() -> bytes:
    image = QImage(8, 6, QImage.Format.Format_RGB888)
    image.fill(QColor("#cc3300"))
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    writer = QImageWriter(buffer, b"PNG")
    assert writer.write(image)
    buffer.close()
    return bytes(data.data())


def test_flujo_real_de_miniaturas_y_edicion(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = synthetic.make_text_pdf(tmp_path / "real.pdf", pages=2, title="Smoke")
    original_bytes = path.read_bytes()

    window = MainWindow(
        open_document=OpenDocument(PyMuPDFEngine()),
        renderer_factory=RenderPage,
    )
    qtbot.addWidget(window)
    window.resize(1100, 850)
    window.show()

    assert window.open_path(path) is True
    qtbot.waitUntil(
        lambda: window.canvas.has_image and window.activity == "Listo",
        timeout=TIMEOUT_MS,
    )

    panel = window.findChild(ThumbnailPanel)
    assert panel is not None
    assert panel.page_count == 2
    qtbot.waitUntil(
        lambda: all(not panel.thumbnail(index).isNull() for index in range(2)),
        timeout=TIMEOUT_MS,
    )

    text = window.add_text_object(PdfRect(50, 50, 300, 120), "Revisado")
    assert isinstance(text, TextObject)
    image = window.add_image_object(
        PdfRect(50, 150, 250, 300), png_bytes(), "image/png", source_path=Path("sello.png")
    )
    assert isinstance(image, ImageObject)
    assert window.is_dirty is True
    assert window.edit_status == "Cambios sin exportar"

    assert window.move_selected_object(PdfRect(60, 160, 260, 310)) is True
    assert window.edit_session is not None
    moved = window.edit_session.object(image.object_id)
    assert moved is not None
    assert moved.rect == PdfRect(60, 160, 260, 310)

    # Deshacer el movimiento y la inserción; rehacer ambos.
    assert window.undo() is True
    restored = window.edit_session.object(image.object_id)
    assert restored is not None
    assert restored.rect == PdfRect(50, 150, 250, 300)
    assert window.undo() is True
    assert session_objects(window) == (text,)
    assert window.redo() is True
    assert window.redo() is True
    assert session_objects(window) == (text, moved)

    # El PDF original no se modifica y no aparece ningún archivo nuevo.
    assert path.read_bytes() == original_bytes
    assert sorted(item.name for item in tmp_path.iterdir()) == ["real.pdf"]

    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Discard,
    )
    window.close_document()
    assert window.edit_session is None


def test_flujo_real_de_redaccion_y_exportacion(qtbot: QtBot, tmp_path: Path) -> None:
    path = synthetic.make_text_pdf(tmp_path / "real.pdf", title="Smoke de redacción")
    original_bytes = path.read_bytes()
    destination = tmp_path / "exportado.pdf"

    window = MainWindow(
        open_document=OpenDocument(PyMuPDFEngine()),
        renderer_factory=RenderPage,
    )
    qtbot.addWidget(window)
    window.resize(1100, 850)
    window.show()

    assert window.open_path(path) is True
    qtbot.waitUntil(
        lambda: window.canvas.has_image and window.activity == "Listo",
        timeout=TIMEOUT_MS,
    )

    redaction = window.add_redaction_object(PdfRect(60, 80, 500, 120))
    assert isinstance(redaction, RedactionObject)
    text = window.add_text_object(PdfRect(60, 80, 500, 120), "REEMPLAZO", TextStyle(font_size=14))
    assert isinstance(text, TextObject)
    assert window.is_dirty is True

    result = window.export_document(destination)

    assert result is not None
    assert result.redaction_count == 1
    assert result.text_count == 1
    assert path.read_bytes() == original_bytes
    assert window.is_dirty is False
    assert window.edit_status == "Sin cambios"

    with pymupdf.open(destination) as document:
        exported = document[0].get_text("text")
    assert "Contrato de prueba" not in exported
    assert "REEMPLAZO" in exported
    assert "Texto nativo seleccionable" in exported

    window.close_document()
    assert window.edit_session is None
