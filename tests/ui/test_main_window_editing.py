"""Pruebas de edición en la ventana principal (RF-007 a RF-014)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QPoint, QPointF, Qt
from PySide6.QtGui import QAction, QColor, QImage, QImageWriter, QWheelEvent
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QMessageBox
from pytestqt.qtbot import QtBot

from bene.application.ports.pdf_engine import OpenedDocument
from bene.application.use_cases.open_document import OpenDocument
from bene.application.use_cases.render_page import RenderPage
from bene.domain.editing import (
    EditObject,
    StrokeObject,
    StrokeStyle,
    TextObject,
    TextStyle,
)
from bene.domain.models import PdfRect
from bene.presentation import main_window as main_window_module
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


def send_ctrl_wheel(window: MainWindow, delta: int) -> None:
    canvas = window.canvas
    event = QWheelEvent(
        QPointF(10, 10),
        QPointF(canvas.mapToGlobal(QPoint(10, 10))),
        QPoint(0, 0),
        QPoint(0, delta),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.ControlModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    QApplication.sendEvent(canvas, event)


def find_action(window: MainWindow, text: str) -> QAction:
    return next(action for action in window.findChildren(QAction) if action.text() == text)


def session_objects(window: MainWindow) -> tuple[EditObject, ...]:
    session = window.edit_session
    assert session is not None
    return session.objects


def canvas_objects(window: MainWindow) -> tuple[EditObject, ...]:
    return window.canvas.objects


def png_bytes() -> bytes:
    image = QImage(4, 3, QImage.Format.Format_RGB888)
    image.fill(QColor("#ff0000"))
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    writer = QImageWriter(buffer, b"PNG")
    assert writer.write(image)
    buffer.close()
    return bytes(data.data())


class FakeTextDialog:
    accepted = True
    next_text = "Texto nuevo"
    next_style = TextStyle(font_size=20, color="#123456")

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        pass

    def exec(self) -> int:
        return (
            int(QDialog.DialogCode.Accepted) if self.accepted else int(QDialog.DialogCode.Rejected)
        )

    @property
    def text(self) -> str:
        return self.next_text

    @property
    def chosen_style(self) -> TextStyle:
        return self.next_style


class TestEstado:
    def test_al_abrir_hay_una_sesion_vacia(self, qtbot: QtBot, tmp_path: Path) -> None:
        window = build_window(qtbot, FakePdfEngine(make_pages(3)))
        open_ready(qtbot, window, tmp_path)

        session = window.edit_session
        assert session is not None
        assert session.objects == ()
        assert window.is_dirty is False
        assert window.edit_status == "Sin cambios"
        assert find_action(window, "Deshacer").isEnabled() is False
        assert find_action(window, "Rehacer").isEnabled() is False
        assert window.properties_panel.object is None

    def test_el_titulo_marca_cambios_sin_exportar(self, qtbot: QtBot, tmp_path: Path) -> None:
        window = build_window(qtbot, FakePdfEngine(make_pages(1)))
        open_ready(qtbot, window, tmp_path)

        assert not window.windowTitle().endswith("*")

        assert window.add_text_object(PdfRect(10, 20, 210, 80), "Hola") is not None
        assert window.windowTitle().endswith("*")

        assert window.undo() is True
        assert not window.windowTitle().endswith("*")

    def test_ctrl_rueda_cambia_el_zoom(self, qtbot: QtBot, tmp_path: Path) -> None:
        window = build_window(qtbot, FakePdfEngine(make_pages(1)))
        open_ready(qtbot, window, tmp_path)
        initial = window.current_scale

        send_ctrl_wheel(window, 120)
        assert window.current_scale > initial

        send_ctrl_wheel(window, -120)
        assert window.current_scale < initial

    def test_al_cerrar_se_libera_la_sesion(self, qtbot: QtBot, tmp_path: Path) -> None:
        window = build_window(qtbot, FakePdfEngine(make_pages(1)))
        open_ready(qtbot, window, tmp_path)

        window.close_document()

        assert window.edit_session is None
        assert window.is_dirty is False
        assert window.edit_status == "Sin cambios"


class TestTexto:
    def test_anade_texto_y_lo_selecciona(self, qtbot: QtBot, tmp_path: Path) -> None:
        window = build_window(qtbot, FakePdfEngine(make_pages(2)))
        open_ready(qtbot, window, tmp_path)
        rect = PdfRect(10, 20, 210, 80)

        obj = window.add_text_object(rect, "Hola", TextStyle(font_size=18))

        assert isinstance(obj, TextObject)
        assert obj is not None
        assert window.edit_session is not None
        assert window.edit_session.objects == (obj,)
        assert window.canvas.objects == (obj,)
        assert window.selected_object_id == obj.object_id
        assert window.canvas.selected_object_id == obj.object_id
        assert window.properties_panel.object == obj
        assert window.is_dirty is True
        assert window.edit_status == "Cambios sin exportar"
        assert find_action(window, "Deshacer").isEnabled() is True

    def test_no_anade_texto_vacio(self, qtbot: QtBot, tmp_path: Path) -> None:
        window = build_window(qtbot, FakePdfEngine(make_pages(1)))
        open_ready(qtbot, window, tmp_path)

        assert window.add_text_object(PdfRect(10, 20, 110, 60), "   ") is None
        assert window.edit_session is not None
        assert window.edit_session.objects == ()

    def test_el_dialogo_usa_la_region_seleccionada(
        self, qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        window = build_window(qtbot, FakePdfEngine(make_pages(1)))
        open_ready(qtbot, window, tmp_path)
        monkeypatch.setattr(main_window_module, "TextDialog", FakeTextDialog)
        region = PdfRect(30, 40, 230, 100)
        window.canvas.set_region(region)

        find_action(window, "Añadir texto…").trigger()

        assert window.edit_session is not None
        objects = window.edit_session.objects
        assert len(objects) == 1
        obj = objects[0]
        assert isinstance(obj, TextObject)
        assert obj.rect == region
        assert obj.text == FakeTextDialog.next_text
        assert obj.style == FakeTextDialog.next_style
        assert window.canvas.region is None
        assert window.canvas.tool is CanvasTool.SELECT

    def test_el_clic_coloca_el_texto_sin_region(
        self, qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        window = build_window(qtbot, FakePdfEngine(make_pages(1)))
        open_ready(qtbot, window, tmp_path)
        monkeypatch.setattr(main_window_module, "TextDialog", FakeTextDialog)

        find_action(window, "Añadir texto…").trigger()
        assert window.canvas.tool is CanvasTool.PLACE
        mapper = window.canvas.mapper
        assert mapper is not None

        qtbot.mouseClick(window.canvas, Qt.MouseButton.LeftButton, pos=QPoint(50, 60))

        assert window.edit_session is not None
        objects = window.edit_session.objects
        assert len(objects) == 1
        obj = objects[0]
        expected_x, expected_y = mapper.to_page_clamped(50, 60)
        assert obj.rect.x0 == pytest.approx(expected_x)
        assert obj.rect.y0 == pytest.approx(expected_y)
        tool: CanvasTool = window.canvas.tool
        assert tool is CanvasTool.SELECT


class TestImagenes:
    def test_anade_una_imagen(self, qtbot: QtBot, tmp_path: Path) -> None:
        window = build_window(qtbot, FakePdfEngine(make_pages(1)))
        open_ready(qtbot, window, tmp_path)
        data = png_bytes()

        obj = window.add_image_object(
            PdfRect(20, 30, 220, 180), data, "image/png", source_path=Path("foto.png")
        )

        assert obj is not None
        assert window.edit_session is not None
        assert window.edit_session.objects == (obj,)
        assert window.properties_panel.object == obj
        assert "Imagen" in window.properties_panel._title.text()

    def test_el_dialogo_inserta_la_imagen_en_la_region(
        self, qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        window = build_window(qtbot, FakePdfEngine(make_pages(1)))
        open_ready(qtbot, window, tmp_path)
        image_path = tmp_path / "foto.png"
        image_path.write_bytes(png_bytes())
        monkeypatch.setattr(
            QFileDialog,
            "getOpenFileName",
            lambda *_args, **_kwargs: (str(image_path), "Imágenes (*.png *.jpg *.jpeg)"),
        )
        region = PdfRect(40, 50, 240, 190)
        window.canvas.set_region(region)

        find_action(window, "Insertar imagen…").trigger()

        assert window.edit_session is not None
        objects = window.edit_session.objects
        assert len(objects) == 1
        assert objects[0].rect == region
        assert window.canvas.region is None


class TestDibujo:
    def test_la_accion_dibujar_activa_la_herramienta(self, qtbot: QtBot, tmp_path: Path) -> None:
        window = build_window(qtbot, FakePdfEngine(make_pages(1)))
        open_ready(qtbot, window, tmp_path)

        assert window.draw_action.isCheckable() is True
        assert window.draw_action.shortcut().toString() == "Ctrl+Shift+D"

        window.draw_action.trigger()

        assert window.canvas.tool is CanvasTool.DRAW
        assert window.draw_action.isChecked() is True

    def test_la_barra_actualiza_color_y_grosor(
        self, qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        window = build_window(qtbot, FakePdfEngine(make_pages(1)))
        open_ready(qtbot, window, tmp_path)

        window.stroke_width_spin.setValue(7.5)

        assert window.stroke_style.width == 7.5
        assert window.canvas.stroke_style.width == 7.5

        monkeypatch.setattr(
            main_window_module.QColorDialog,
            "getColor",
            lambda *_args, **_kwargs: QColor("#00ff00"),
        )
        window.stroke_color_button.click()

        assert window.stroke_style.color == "#00ff00"
        assert window.canvas.stroke_style.color == "#00ff00"
        assert window.stroke_color_button.text() == "#00ff00"

    def test_anade_un_trazo_y_lo_selecciona(self, qtbot: QtBot, tmp_path: Path) -> None:
        window = build_window(qtbot, FakePdfEngine(make_pages(1)))
        open_ready(qtbot, window, tmp_path)
        style = StrokeStyle(color="#123456", width=3.0)

        obj = window.add_stroke_object(((10.0, 20.0), (50.0, 40.0)), style)

        assert isinstance(obj, StrokeObject)
        assert obj is not None
        assert obj.style == style
        assert session_objects(window) == (obj,)
        assert canvas_objects(window) == (obj,)
        assert window.selected_object_id == obj.object_id
        assert window.properties_panel.object == obj
        assert window.properties_panel._title.text() == "Trazo"
        assert "3" in window.properties_panel._preview.text()
        assert window.is_dirty is True

    def test_el_lienzo_crea_el_trazo_y_mantiene_la_herramienta(
        self, qtbot: QtBot, tmp_path: Path
    ) -> None:
        window = build_window(qtbot, FakePdfEngine(make_pages(1)))
        open_ready(qtbot, window, tmp_path)
        window.stroke_width_spin.setValue(5.0)
        window.draw_action.trigger()
        mapper = window.canvas.mapper
        assert mapper is not None
        start_x, start_y = mapper.to_view(50, 50)
        end_x, end_y = mapper.to_view(150, 50)

        qtbot.mousePress(
            window.canvas, Qt.MouseButton.LeftButton, pos=QPoint(round(start_x), round(start_y))
        )
        qtbot.mouseMove(window.canvas, QPoint(round(end_x), round(end_y)))
        qtbot.mouseRelease(
            window.canvas, Qt.MouseButton.LeftButton, pos=QPoint(round(end_x), round(end_y))
        )

        assert window.canvas.tool is CanvasTool.DRAW
        objects = session_objects(window)
        assert len(objects) == 1
        obj = objects[0]
        assert isinstance(obj, StrokeObject)
        assert obj.style.width == 5.0
        assert obj.points[0] == pytest.approx((50.0, 50.0), abs=2)
        assert obj.points[-1] == pytest.approx((150.0, 50.0), abs=2)

    def test_mueve_redimensiona_y_elimina_un_trazo(self, qtbot: QtBot, tmp_path: Path) -> None:
        window = build_window(qtbot, FakePdfEngine(make_pages(1)))
        open_ready(qtbot, window, tmp_path)
        obj = window.add_stroke_object(((10.0, 20.0), (50.0, 40.0)), StrokeStyle(width=2.0))
        assert obj is not None

        assert window.move_selected_object(PdfRect(19, 24, 61, 46)) is True
        moved = window.edit_session.object(obj.object_id) if window.edit_session else None
        assert isinstance(moved, StrokeObject)
        assert moved.points == ((20.0, 25.0), (60.0, 45.0))

        assert window.resize_selected_object(PdfRect(0, 0, 82, 42)) is True
        resized = window.edit_session.object(obj.object_id) if window.edit_session else None
        assert isinstance(resized, StrokeObject)
        assert resized.points == ((1.0, 1.0), (81.0, 41.0))

        assert window.delete_selected_object() is True
        assert session_objects(window) == ()
        assert window.undo() is True
        assert session_objects(window) == (resized,)

    def test_el_dialogo_de_texto_recuerda_el_ultimo_estilo(
        self, qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        window = build_window(qtbot, FakePdfEngine(make_pages(1)))
        open_ready(qtbot, window, tmp_path)
        seen: list[TextStyle | None] = []

        class RecordingTextDialog(FakeTextDialog):
            def __init__(self, *_args: object, **kwargs: object) -> None:
                style = kwargs.get("style")
                if style is not None and not isinstance(style, TextStyle):
                    raise TypeError("Estilo de texto inválido")
                seen.append(style)

        monkeypatch.setattr(main_window_module, "TextDialog", RecordingTextDialog)
        window.canvas.set_region(PdfRect(10, 20, 210, 80))
        find_action(window, "Añadir texto…").trigger()
        window.canvas.set_region(PdfRect(10, 20, 210, 80))
        find_action(window, "Añadir texto…").trigger()

        assert seen == [None, FakeTextDialog.next_style]


class TestTransformaciones:
    def test_mueve_y_redimensiona_el_objeto_seleccionado(
        self, qtbot: QtBot, tmp_path: Path
    ) -> None:
        window = build_window(qtbot, FakePdfEngine(make_pages(1)))
        open_ready(qtbot, window, tmp_path)
        obj = window.add_text_object(PdfRect(10, 20, 210, 80), "Hola")
        assert obj is not None

        window.move_selected_object(PdfRect(50, 60, 250, 120))
        moved = window.edit_session.object(obj.object_id) if window.edit_session else None
        assert moved is not None
        assert moved.rect == PdfRect(50, 60, 250, 120)

        window.resize_selected_object(PdfRect(50, 60, 350, 160))
        resized = window.edit_session.object(obj.object_id) if window.edit_session else None
        assert resized is not None
        assert resized.rect == PdfRect(50, 60, 350, 160)

    def test_el_arrastre_del_lienzo_actualiza_la_sesion(self, qtbot: QtBot, tmp_path: Path) -> None:
        window = build_window(qtbot, FakePdfEngine(make_pages(1)))
        open_ready(qtbot, window, tmp_path)
        obj = window.add_text_object(PdfRect(100, 100, 300, 160), "Hola")
        assert obj is not None
        mapper = window.canvas.mapper
        assert mapper is not None
        start_x, start_y = mapper.to_view(200, 130)
        end_x, end_y = mapper.to_view(230, 150)

        qtbot.mousePress(
            window.canvas, Qt.MouseButton.LeftButton, pos=QPoint(round(start_x), round(start_y))
        )
        qtbot.mouseMove(window.canvas, QPoint(round(end_x), round(end_y)))
        qtbot.mouseRelease(
            window.canvas, Qt.MouseButton.LeftButton, pos=QPoint(round(end_x), round(end_y))
        )

        assert window.edit_session is not None
        moved = window.edit_session.object(obj.object_id)
        assert moved is not None
        assert moved.rect.x0 == pytest.approx(130, abs=2)
        assert moved.rect.y0 == pytest.approx(120, abs=2)

    def test_el_panel_de_propiedades_aplica_la_geometria(
        self, qtbot: QtBot, tmp_path: Path
    ) -> None:
        window = build_window(qtbot, FakePdfEngine(make_pages(1)))
        open_ready(qtbot, window, tmp_path)
        obj = window.add_text_object(PdfRect(10, 20, 210, 80), "Hola")
        assert obj is not None
        panel = window.properties_panel

        panel._x.setValue(40)
        panel._y.setValue(50)
        panel._width.setValue(200)
        panel._height.setValue(90)
        panel._apply.click()

        assert window.edit_session is not None
        updated = window.edit_session.object(obj.object_id)
        assert updated is not None
        assert updated.rect == PdfRect(40, 50, 240, 140)


class TestHistorial:
    def test_deshacer_y_rehacer(self, qtbot: QtBot, tmp_path: Path) -> None:
        window = build_window(qtbot, FakePdfEngine(make_pages(1)))
        open_ready(qtbot, window, tmp_path)
        obj = window.add_text_object(PdfRect(10, 20, 210, 80), "Hola")
        assert obj is not None

        assert window.undo() is True
        assert window.edit_session is not None
        assert session_objects(window) == ()
        assert canvas_objects(window) == ()
        assert window.is_dirty is False
        assert window.edit_status == "Sin cambios"

        assert window.redo() is True
        assert session_objects(window) == (obj,)
        assert canvas_objects(window) == (obj,)
        assert window.is_dirty is True

    def test_elimina_y_deshace(self, qtbot: QtBot, tmp_path: Path) -> None:
        window = build_window(qtbot, FakePdfEngine(make_pages(1)))
        open_ready(qtbot, window, tmp_path)
        obj = window.add_text_object(PdfRect(10, 20, 210, 80), "Hola")
        assert obj is not None

        assert window.delete_selected_object() is True
        assert window.edit_session is not None
        assert session_objects(window) == ()
        assert window.selected_object_id is None

        assert window.undo() is True
        assert session_objects(window) == (obj,)

    def test_sin_seleccion_no_elimina(self, qtbot: QtBot, tmp_path: Path) -> None:
        window = build_window(qtbot, FakePdfEngine(make_pages(1)))
        open_ready(qtbot, window, tmp_path)

        assert window.delete_selected_object() is False

    def test_los_objetos_pertenecen_a_su_pagina(self, qtbot: QtBot, tmp_path: Path) -> None:
        window = build_window(qtbot, FakePdfEngine(make_pages(2)))
        open_ready(qtbot, window, tmp_path)
        first = window.add_text_object(PdfRect(10, 20, 210, 80), "Primera")
        window.go_to_page(1)
        qtbot.waitUntil(lambda: window.page_index == 1 and window.activity == "Listo")
        second = window.add_text_object(PdfRect(10, 20, 210, 80), "Segunda")
        assert first is not None and second is not None

        window.go_to_page(0)
        qtbot.waitUntil(lambda: window.page_index == 0 and window.activity == "Listo")

        assert window.canvas.objects == (first,)
        assert window.edit_session is not None
        assert window.edit_session.objects_on_page(1) == (second,)


class TestAvisoDeCambios:
    def test_cancelar_la_apertura_conserva_el_documento(
        self, qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        window = build_window(qtbot, FakePdfEngine(make_pages(1)))
        original = open_ready(qtbot, window, tmp_path, "original.pdf")
        window.add_text_object(PdfRect(10, 20, 210, 80), "Hola")
        monkeypatch.setattr(
            QMessageBox,
            "warning",
            lambda *_args, **_kwargs: QMessageBox.StandardButton.Cancel,
        )

        assert window.open_path(write_pdf(tmp_path, "otro.pdf")) is False

        assert window.document_info is not None
        assert window.document_info.path == original
        assert window.is_dirty is True

    def test_descartar_abre_el_nuevo_documento(
        self, qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        engine = FakePdfEngine(make_pages(1))
        window = build_window(qtbot, engine)
        open_ready(qtbot, window, tmp_path, "original.pdf")
        window.add_text_object(PdfRect(10, 20, 210, 80), "Hola")
        first_document = engine.documents[0]
        monkeypatch.setattr(
            QMessageBox,
            "warning",
            lambda *_args, **_kwargs: QMessageBox.StandardButton.Discard,
        )

        assert window.open_path(write_pdf(tmp_path, "otro.pdf")) is True

        assert first_document.closed is True
        assert window.is_dirty is False
        assert window.edit_session is not None
        assert window.edit_session.objects == ()

    def test_cancelar_el_cierre_conserva_el_documento(
        self, qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        window = build_window(qtbot, FakePdfEngine(make_pages(1)))
        open_ready(qtbot, window, tmp_path)
        window.add_text_object(PdfRect(10, 20, 210, 80), "Hola")
        monkeypatch.setattr(
            QMessageBox,
            "warning",
            lambda *_args, **_kwargs: QMessageBox.StandardButton.Cancel,
        )

        assert window.close() is False
        assert window.document_info is not None
