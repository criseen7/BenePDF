"""Pruebas de redacción y exportación en la ventana principal (RF-009, RF-010)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QFileDialog, QMessageBox
from pytestqt.qtbot import QtBot

from bene.application.ports.pdf_engine import OpenedDocument
from bene.application.use_cases.open_document import OpenDocument
from bene.application.use_cases.render_page import RenderPage
from bene.domain.editing import RedactionObject
from bene.domain.models import PdfRect
from bene.presentation.main_window import MainWindow
from bene.presentation.viewer.pdf_canvas import CanvasTool
from bene.presentation.workers.render_worker import PageRenderer
from tests.unit.fakes import FakePdfEngine, make_pages

pytestmark = pytest.mark.ui

TIMEOUT_MS = 5000


def build_window(
    qtbot: QtBot,
    engine: FakePdfEngine,
    renderer_factory: Callable[[OpenedDocument], PageRenderer] = RenderPage,
) -> MainWindow:
    window = MainWindow(
        open_document=OpenDocument(engine),
        renderer_factory=renderer_factory,
    )
    qtbot.addWidget(window)
    window.resize(1100, 850)
    window.show()
    return window


def write_pdf(tmp_path: Path, name: str = "documento.pdf") -> Path:
    path = tmp_path / name
    path.write_bytes(b"%PDF-1.4\n")
    return path


def open_ready(
    qtbot: QtBot, window: MainWindow, tmp_path: Path, name: str = "documento.pdf"
) -> Path:
    path = write_pdf(tmp_path, name)
    assert window.open_path(path) is True
    qtbot.waitUntil(
        lambda: window.canvas.has_image and window.activity == "Listo",
        timeout=TIMEOUT_MS,
    )
    return path


def find_action(window: MainWindow, text: str) -> QAction:
    return next(action for action in window.findChildren(QAction) if action.text() == text)


def drag(
    qtbot: QtBot,
    window: MainWindow,
    rect: PdfRect,
) -> None:
    mapper = window.canvas.mapper
    assert mapper is not None
    start_x, start_y = mapper.to_view(rect.x0, rect.y0)
    end_x, end_y = mapper.to_view(rect.x1, rect.y1)
    qtbot.mousePress(
        window.canvas, Qt.MouseButton.LeftButton, pos=QPoint(round(start_x), round(start_y))
    )
    qtbot.mouseMove(window.canvas, QPoint(round(end_x), round(end_y)))
    qtbot.mouseRelease(
        window.canvas, Qt.MouseButton.LeftButton, pos=QPoint(round(end_x), round(end_y))
    )


class TestRedaccion:
    def test_la_herramienta_redactar_se_activa(self, qtbot: QtBot, tmp_path: Path) -> None:
        window = build_window(qtbot, FakePdfEngine(make_pages(1)))
        open_ready(qtbot, window, tmp_path)

        action = find_action(window, "Redactar región")
        action.trigger()

        assert window.canvas.tool is CanvasTool.REDACT
        assert action.isChecked() is True

    def test_marca_una_region_tras_confirmar(
        self, qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        window = build_window(qtbot, FakePdfEngine(make_pages(1)))
        open_ready(qtbot, window, tmp_path)
        messages: list[str] = []

        def confirm(_parent: object, _title: str, text: str, *_args: object) -> object:
            messages.append(text)
            return QMessageBox.StandardButton.Ok

        monkeypatch.setattr(QMessageBox, "warning", confirm)
        find_action(window, "Redactar región").trigger()

        drag(qtbot, window, PdfRect(50, 60, 150, 100))

        session = window.edit_session
        assert session is not None
        objects = session.objects
        assert len(objects) == 1
        obj = objects[0]
        assert isinstance(obj, RedactionObject)
        assert obj.rect.x0 == pytest.approx(50, abs=1)
        assert obj.rect.y0 == pytest.approx(60, abs=1)
        assert obj.rect.x1 == pytest.approx(150, abs=1)
        assert obj.rect.y1 == pytest.approx(100, abs=1)
        assert window.selected_object_id == obj.object_id
        assert window.canvas.objects == (obj,)
        assert window.properties_panel.object == obj
        assert window.is_dirty is True
        assert messages and "permanente" in messages[0]

    def test_cancelar_la_confirmacion_no_marca_nada(
        self, qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        window = build_window(qtbot, FakePdfEngine(make_pages(1)))
        open_ready(qtbot, window, tmp_path)
        monkeypatch.setattr(
            QMessageBox,
            "warning",
            lambda *_args, **_kwargs: QMessageBox.StandardButton.Cancel,
        )
        find_action(window, "Redactar región").trigger()

        drag(qtbot, window, PdfRect(50, 60, 150, 100))

        assert window.edit_session is not None
        assert window.edit_session.objects == ()
        assert window.is_dirty is False

    def test_la_redaccion_se_puede_mover_y_deshacer(self, qtbot: QtBot, tmp_path: Path) -> None:
        window = build_window(qtbot, FakePdfEngine(make_pages(1)))
        open_ready(qtbot, window, tmp_path)
        obj = window.add_redaction_object(PdfRect(20, 30, 120, 80))
        assert obj is not None

        assert window.move_selected_object(PdfRect(60, 70, 160, 120)) is True
        moved = window.edit_session.object(obj.object_id) if window.edit_session else None
        assert moved is not None
        assert moved.rect == PdfRect(60, 70, 160, 120)

        assert window.undo() is True
        restored = window.edit_session.object(obj.object_id) if window.edit_session else None
        assert restored is not None
        assert restored.rect == PdfRect(20, 30, 120, 80)


class TestExportacion:
    def test_exporta_una_copia_y_deja_la_sesion_limpia(self, qtbot: QtBot, tmp_path: Path) -> None:
        engine = FakePdfEngine(make_pages(2))
        window = build_window(qtbot, engine)
        source = open_ready(qtbot, window, tmp_path)
        original = source.read_bytes()
        window.add_text_object(PdfRect(10, 20, 210, 80), "Hola")
        window.add_redaction_object(PdfRect(20, 30, 120, 80))
        destination = tmp_path / "copia.pdf"

        result = window.export_document(destination)

        assert result is not None
        assert result.destination == destination
        assert result.text_count == 1
        assert result.redaction_count == 1
        assert destination.exists()
        assert source.read_bytes() == original
        assert window.is_dirty is False
        assert window.edit_status == "Sin cambios"
        assert "Exportado" in window.activity
        assert engine.documents[0].export_calls[0][0] == destination

    def test_no_permite_exportar_sobre_el_original(
        self, qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        engine = FakePdfEngine(make_pages(1))
        window = build_window(qtbot, engine)
        source = open_ready(qtbot, window, tmp_path)
        original = source.read_bytes()
        window.add_text_object(PdfRect(10, 20, 210, 80), "Hola")
        shown: list[str] = []
        monkeypatch.setattr(
            QMessageBox,
            "critical",
            lambda _parent, _title, text: shown.append(text),
        )

        result = window.export_document(source)

        assert result is None
        assert source.read_bytes() == original
        assert engine.documents[0].export_calls == []
        assert window.is_dirty is True
        assert shown and "distinto del PDF original" in shown[0]

    def test_la_accion_exportar_usa_el_dialogo_y_confirma_redacciones(
        self, qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        window = build_window(qtbot, FakePdfEngine(make_pages(1)))
        open_ready(qtbot, window, tmp_path)
        window.add_redaction_object(PdfRect(20, 30, 120, 80))
        destination = tmp_path / "exportado.pdf"
        monkeypatch.setattr(
            QFileDialog,
            "getSaveFileName",
            lambda *_args, **_kwargs: (str(destination), "Documentos PDF (*.pdf)"),
        )
        confirmations: list[str] = []

        def confirm(_parent: object, _title: str, text: str, *_args: object) -> object:
            confirmations.append(text)
            return QMessageBox.StandardButton.Ok

        monkeypatch.setattr(QMessageBox, "warning", confirm)

        find_action(window, "Exportar como…").trigger()

        assert destination.exists()
        assert confirmations and "redacción" in confirmations[0]
        assert window.is_dirty is False

    def test_cancelar_la_confirmacion_de_redaccion_no_exporta(
        self, qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        engine = FakePdfEngine(make_pages(1))
        window = build_window(qtbot, engine)
        open_ready(qtbot, window, tmp_path)
        window.add_redaction_object(PdfRect(20, 30, 120, 80))
        destination = tmp_path / "exportado.pdf"
        monkeypatch.setattr(
            QFileDialog,
            "getSaveFileName",
            lambda *_args, **_kwargs: (str(destination), "Documentos PDF (*.pdf)"),
        )
        monkeypatch.setattr(
            QMessageBox,
            "warning",
            lambda *_args, **_kwargs: QMessageBox.StandardButton.Cancel,
        )

        assert window._export_as() is False

        assert not destination.exists()
        assert engine.documents[0].export_calls == []
        assert window.is_dirty is True

    def test_un_fallo_de_exportacion_mantiene_la_sesion_sucia(
        self, qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        engine = FakePdfEngine(make_pages(1))
        window = build_window(qtbot, engine)
        open_ready(qtbot, window, tmp_path)
        window.add_text_object(PdfRect(10, 20, 210, 80), "Hola")
        engine.documents[0].export_should_fail = True
        shown: list[str] = []
        monkeypatch.setattr(
            QMessageBox,
            "critical",
            lambda _parent, _title, text: shown.append(text),
        )

        assert window.export_document(tmp_path / "copia.pdf") is None

        assert shown
        assert window.is_dirty is True

    def test_el_nombre_por_defecto_no_pisa_una_exportacion_anterior(
        self, qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        window = build_window(qtbot, FakePdfEngine(make_pages(1)))
        open_ready(qtbot, window, tmp_path)
        (tmp_path / "documento-editado.pdf").write_bytes(b"EXPORTACION ANTERIOR")
        offered: list[str] = []

        def choose(_parent: object, _title: str, directory: str, *_args: object) -> tuple[str, str]:
            offered.append(directory)
            return ("", "")

        monkeypatch.setattr(QFileDialog, "getSaveFileName", choose)

        assert window._export_as() is False

        assert Path(offered[0]).name == "documento-editado-2.pdf"

    def test_el_cierre_permite_guardar_una_copia(
        self, qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        window = build_window(qtbot, FakePdfEngine(make_pages(1)))
        open_ready(qtbot, window, tmp_path)
        window.add_text_object(PdfRect(10, 20, 210, 80), "Hola")
        destination = tmp_path / "guardado.pdf"
        monkeypatch.setattr(
            QFileDialog,
            "getSaveFileName",
            lambda *_args, **_kwargs: (str(destination), "Documentos PDF (*.pdf)"),
        )
        monkeypatch.setattr(
            QMessageBox,
            "warning",
            lambda *_args, **_kwargs: QMessageBox.StandardButton.Save,
        )

        assert window.close() is True

        assert destination.exists()
        assert window.edit_session is None

    def test_un_pdf_cifrado_no_se_puede_exportar(self, qtbot: QtBot, tmp_path: Path) -> None:
        window = build_window(qtbot, FakePdfEngine(make_pages(1), encrypted=True))
        open_ready(qtbot, window, tmp_path)

        action = find_action(window, "Exportar como…")
        assert action.isEnabled() is False
        assert "cifrado" in action.statusTip()
