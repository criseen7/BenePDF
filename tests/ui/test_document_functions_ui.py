"""Pruebas de interfaz de las funciones de documento (RF-013, RF-020 a RF-023)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from PySide6.QtCore import QBuffer, QByteArray, QIODevice
from PySide6.QtGui import QAction, QColor, QImage, QImageWriter
from PySide6.QtWidgets import QDialog, QMessageBox, QPushButton
from pytestqt.qtbot import QtBot

from bene.application.ports.pdf_engine import (
    EmbeddedImage,
    OpenedDocument,
    SearchMatch,
)
from bene.application.use_cases.open_document import OpenDocument
from bene.application.use_cases.render_page import RenderPage
from bene.domain.editing import ImageReplacementObject
from bene.domain.models import DocumentInfo, PdfRect
from bene.presentation import main_window as main_window_module
from bene.presentation.dialogs.document_info_dialog import (
    DocumentInfoDialog,
    format_file_size,
)
from bene.presentation.dialogs.image_replacement_dialog import ImageReplacementDialog
from bene.presentation.images import LoadedImage
from bene.presentation.main_window import MainWindow
from bene.presentation.widgets.search_panel import SearchPanel
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


def png_bytes(color: str = "#ff0000", width: int = 4, height: int = 3) -> bytes:
    image = QImage(width, height, QImage.Format.Format_RGB888)
    image.fill(QColor(color))
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    writer = QImageWriter(buffer, b"PNG")
    assert writer.write(image)
    buffer.close()
    return bytes(data.data())


def match(page_index: int, x0: float = 10.0, y0: float = 20.0) -> SearchMatch:
    return SearchMatch(
        page_index=page_index,
        rect=PdfRect(x0, y0, x0 + 80, y0 + 14),
        snippet=f"texto en página {page_index + 1}",
    )


class TestBusqueda:
    def test_muestra_y_navega_por_las_coincidencias(self, qtbot: QtBot, tmp_path: Path) -> None:
        engine = FakePdfEngine(make_pages(3))
        window = build_window(qtbot, engine)
        open_ready(qtbot, window, tmp_path)
        document = engine.documents[0]
        document.search_results = (match(0), match(1), match(2))

        window.search_text("texto")
        qtbot.waitUntil(lambda: len(window.search_matches) == 3, timeout=TIMEOUT_MS)

        assert document.search_calls == ["texto"]
        assert window.search_panel.matches == document.search_results
        assert window.search_panel.current_index == 0
        assert window.current_search_match == document.search_results[0]
        assert window.search_panel.status_text == "Coincidencia 1 de 3 · página 1"
        assert window.canvas.search_highlights == (match(0).rect,)
        assert window.canvas.current_search_highlight == match(0).rect

        window.find_next()
        qtbot.waitUntil(lambda: window.page_index == 1, timeout=TIMEOUT_MS)
        qtbot.waitUntil(
            lambda: window.canvas.current_search_highlight == match(1).rect,
            timeout=TIMEOUT_MS,
        )
        assert window.search_panel.current_index == 1
        assert window.current_search_match == document.search_results[1]

        window.find_previous()
        qtbot.waitUntil(lambda: window.page_index == 0, timeout=TIMEOUT_MS)
        assert window.search_panel.current_index == 0

    def test_sin_coincidencias(self, qtbot: QtBot, tmp_path: Path) -> None:
        engine = FakePdfEngine(make_pages(2))
        window = build_window(qtbot, engine)
        open_ready(qtbot, window, tmp_path)
        engine.documents[0].search_results = ()

        window.search_text("inexistente")
        qtbot.waitUntil(
            lambda: window.search_panel.status_text == "Sin coincidencias para «inexistente»",
            timeout=TIMEOUT_MS,
        )

        assert window.search_matches == ()
        assert window.current_search_match is None
        assert window.canvas.search_highlights == ()

    def test_un_fallo_de_busqueda_se_muestra_en_el_panel(
        self, qtbot: QtBot, tmp_path: Path
    ) -> None:
        engine = FakePdfEngine(make_pages(2))
        window = build_window(qtbot, engine)
        open_ready(qtbot, window, tmp_path)

        def fail(_query: str) -> tuple[SearchMatch, ...]:
            raise RuntimeError("motor no disponible")

        engine.documents[0].search_text = fail  # type: ignore[assignment]

        window.search_text("texto")
        qtbot.waitUntil(
            lambda: window.search_panel.status_text.startswith("No se pudo buscar:"),
            timeout=TIMEOUT_MS,
        )

        assert "motor no disponible" in window.search_panel.status_text
        assert window.search_matches == ()

    def test_una_coincidencia_en_una_pagina_eliminada_no_navega(
        self, qtbot: QtBot, tmp_path: Path
    ) -> None:
        engine = FakePdfEngine(make_pages(3))
        window = build_window(qtbot, engine)
        open_ready(qtbot, window, tmp_path)
        engine.documents[0].search_results = (match(0), match(2))

        window.search_text("texto")
        qtbot.waitUntil(lambda: len(window.search_matches) == 2, timeout=TIMEOUT_MS)

        session = window.edit_session
        assert session is not None
        session.delete_page(2)

        window.find_next()
        assert window.page_index == 0
        assert "eliminada" in window.activity

    def test_la_busqueda_vacia_no_consulta_el_documento(self, qtbot: QtBot, tmp_path: Path) -> None:
        engine = FakePdfEngine(make_pages(1))
        window = build_window(qtbot, engine)
        open_ready(qtbot, window, tmp_path)

        window.search_text("   ")

        assert engine.documents[0].search_calls == []
        assert window.search_matches == ()


class TestPanelDeBusqueda:
    def test_pide_un_texto_antes_de_buscar(self, qtbot: QtBot) -> None:
        panel = SearchPanel()
        qtbot.addWidget(panel)

        panel._request_search()

        assert panel.status_text == "Escribe un texto para buscar"

    def test_la_navegacion_es_circular(self, qtbot: QtBot) -> None:
        panel = SearchPanel()
        qtbot.addWidget(panel)
        panel.set_results("texto", (match(0), match(1)))

        assert panel.current_index == 0
        panel.previous_match()
        assert panel.current_index == 1
        panel.next_match()
        assert panel.current_index == 0

    def test_clear_restaura_el_estado_inicial(self, qtbot: QtBot) -> None:
        panel = SearchPanel()
        qtbot.addWidget(panel)
        panel.set_results("texto", (match(0),))

        panel.clear()

        assert panel.matches == ()
        assert panel.current_match is None
        assert panel.status_text == "Escribe un texto y pulsa Buscar"


class TestOperacionesDePaginas:
    def test_rotar_la_pagina_actual(self, qtbot: QtBot, tmp_path: Path) -> None:
        engine = FakePdfEngine(make_pages(2))
        window = build_window(qtbot, engine)
        open_ready(qtbot, window, tmp_path)

        assert window.rotate_current_page(90) is True

        session = window.edit_session
        assert session is not None
        assert session.page_arrangement.rotation(0) == 90
        assert window.is_dirty is True
        assert "842 × 595 pt" in window.page_description
        qtbot.waitUntil(
            lambda: any(
                page_index == 0 and rotation == 90
                for page_index, _scale, rotation in engine.documents[0].render_calls
            ),
            timeout=TIMEOUT_MS,
        )

    def test_mover_la_pagina_actual(self, qtbot: QtBot, tmp_path: Path) -> None:
        engine = FakePdfEngine(make_pages(3))
        window = build_window(qtbot, engine)
        open_ready(qtbot, window, tmp_path)

        assert window.move_current_page(1) is True

        session = window.edit_session
        assert session is not None
        assert session.page_arrangement.order == (1, 0, 2)
        assert window.page_index == 1
        assert window.is_dirty is True

        assert window.move_current_page(1) is True
        assert session.page_arrangement.order == (1, 2, 0)
        assert window.page_index == 2

    def test_los_limites_de_movimiento_no_cambian_nada(self, qtbot: QtBot, tmp_path: Path) -> None:
        engine = FakePdfEngine(make_pages(2))
        window = build_window(qtbot, engine)
        open_ready(qtbot, window, tmp_path)

        assert window.move_current_page(-1) is False
        assert window.page_index == 0
        assert window.is_dirty is False

    def test_eliminar_pide_confirmacion_y_avisa_de_los_objetos(
        self,
        qtbot: QtBot,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        engine = FakePdfEngine(make_pages(3))
        window = build_window(qtbot, engine)
        open_ready(qtbot, window, tmp_path)
        session = window.edit_session
        assert session is not None
        session.add_text(1, PdfRect(10, 10, 110, 50), "Hola")
        messages: list[str] = []

        def confirm(_parent: object, _title: str, text: str, *_args: object) -> object:
            messages.append(text)
            return QMessageBox.StandardButton.Ok

        monkeypatch.setattr(QMessageBox, "warning", confirm)

        window.go_to_page(1)
        assert window.delete_current_page() is True

        assert session.page_arrangement.order == (0, 2)
        assert window.output_page_count == 2
        assert "1 objeto(s)" in messages[-1]
        assert "El PDF original no cambia" in messages[-1]
        assert window.is_dirty is True

    def test_cancelar_la_eliminacion_no_cambia_la_sesion(
        self,
        qtbot: QtBot,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        engine = FakePdfEngine(make_pages(2))
        window = build_window(qtbot, engine)
        open_ready(qtbot, window, tmp_path)
        monkeypatch.setattr(
            QMessageBox,
            "warning",
            lambda *_args, **_kwargs: QMessageBox.StandardButton.Cancel,
        )

        assert window.delete_current_page() is False

        session = window.edit_session
        assert session is not None
        assert session.output_page_count == 2
        assert window.is_dirty is False

    def test_deshacer_la_eliminacion(
        self, qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        engine = FakePdfEngine(make_pages(3))
        window = build_window(qtbot, engine)
        open_ready(qtbot, window, tmp_path)
        monkeypatch.setattr(
            QMessageBox,
            "warning",
            lambda *_args, **_kwargs: QMessageBox.StandardButton.Ok,
        )
        window.go_to_page(1)
        assert window.delete_current_page() is True

        assert window.undo() is True

        session = window.edit_session
        assert session is not None
        assert session.page_arrangement.order == (0, 1, 2)
        assert window.output_page_count == 3

    def test_no_se_puede_eliminar_la_ultima_pagina(self, qtbot: QtBot, tmp_path: Path) -> None:
        engine = FakePdfEngine(make_pages(1))
        window = build_window(qtbot, engine)
        open_ready(qtbot, window, tmp_path)

        assert window.delete_current_page() is False
        assert find_action(window, "Eliminar página…").isEnabled() is False

    def test_las_acciones_de_pagina_reflejan_los_limites(
        self, qtbot: QtBot, tmp_path: Path
    ) -> None:
        engine = FakePdfEngine(make_pages(2))
        window = build_window(qtbot, engine)
        open_ready(qtbot, window, tmp_path)

        assert find_action(window, "Mover página arriba").isEnabled() is False
        assert find_action(window, "Mover página abajo").isEnabled() is True
        window.go_to_page(1)
        assert find_action(window, "Mover página arriba").isEnabled() is True
        assert find_action(window, "Mover página abajo").isEnabled() is False

    def test_extraer_paginas_no_marca_la_sesion(self, qtbot: QtBot, tmp_path: Path) -> None:
        engine = FakePdfEngine(make_pages(3))
        window = build_window(qtbot, engine)
        open_ready(qtbot, window, tmp_path)
        destination = tmp_path / "extracto.pdf"

        result = window.extract_pages("1, 3", destination)

        assert result is not None
        assert result.page_count == 2
        assert result.destination == destination.absolute()
        arrangement = engine.documents[0].export_arrangements[-1]
        assert arrangement is not None
        assert arrangement.order == (0, 2)
        assert window.is_dirty is False
        assert window.edit_status == "Sin cambios"

    def test_extraer_conserva_la_rotacion_adicional(self, qtbot: QtBot, tmp_path: Path) -> None:
        engine = FakePdfEngine(make_pages(3))
        window = build_window(qtbot, engine)
        open_ready(qtbot, window, tmp_path)
        window.go_to_page(2)
        window.rotate_current_page(180)

        result = window.extract_pages("3", tmp_path / "pagina.pdf")

        assert result is not None
        arrangement = engine.documents[0].export_arrangements[-1]
        assert arrangement is not None
        assert arrangement.order == (2,)
        assert arrangement.rotation(2) == 180

    def test_el_nombre_de_extraccion_no_pisa_archivos(self, qtbot: QtBot, tmp_path: Path) -> None:
        engine = FakePdfEngine(make_pages(1))
        window = build_window(qtbot, engine)
        path = open_ready(qtbot, window, tmp_path)
        info = window.document_info
        assert info is not None

        first = window._default_extract_path(info)
        assert first.name == "documento-paginas.pdf"
        first.write_bytes(b"%PDF-1.4\n")

        second = window._default_extract_path(info)
        assert second.name == "documento-paginas-2.pdf"
        assert second != path


class TestInformacionDelDocumento:
    def test_formatea_el_tamano(self) -> None:
        assert format_file_size(0) == "0 B"
        assert format_file_size(1023) == "1023 B"
        assert format_file_size(1024) == "1.0 KB"
        assert format_file_size(1536) == "1.5 KB"
        assert format_file_size(5 * 1024 * 1024) == "5.0 MB"

    def test_el_dialogo_muestra_los_datos(self, tmp_path: Path) -> None:
        info = DocumentInfo(
            path=tmp_path / "documento.pdf",
            page_count=3,
            file_size_bytes=2048,
            metadata={"title": "Mi documento", "author": "Ana"},
            encrypted=False,
        )

        dialog = DocumentInfoDialog(
            info,
            page_size=(595.0, 842.0),
            output_page_count=2,
        )

        assert dialog.fields["Páginas"] == "3"
        assert dialog.fields["Páginas al exportar"] == "2 (se eliminarán 1)"
        assert dialog.fields["Tamaño"] == "2.0 KB"
        assert dialog.fields["Página actual"] == "595 × 842 pt"
        assert dialog.fields["Protección"] == "Sin cifrado"
        assert dialog.fields["Título"] == "Mi documento"
        assert dialog.fields["Autor"] == "Ana"

    def test_la_ventana_pasa_la_disposicion_actual(
        self,
        qtbot: QtBot,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        engine = FakePdfEngine(make_pages(3))
        window = build_window(qtbot, engine)
        open_ready(qtbot, window, tmp_path)
        window.go_to_page(1)
        session = window.edit_session
        assert session is not None
        session.delete_page(2)
        captured: dict[str, object] = {}

        class FakeDialog:
            def __init__(self, info: DocumentInfo, **kwargs: object) -> None:
                captured["info"] = info
                captured.update(kwargs)

            def exec(self) -> int:
                return 0

        monkeypatch.setattr(main_window_module, "DocumentInfoDialog", FakeDialog)

        window.show_document_info()

        assert captured["info"] is window.document_info
        assert captured["page_size"] == (595.0, 842.0)
        assert captured["output_page_count"] == 2
        assert captured["parent"] is window


class TestReemplazoDeImagen:
    def test_el_dialogo_avisa_de_imagenes_compartidas(self, qtbot: QtBot) -> None:
        image = EmbeddedImage(
            image_id="5",
            page_index=0,
            rect=PdfRect(72, 72, 272, 172),
            pixel_width=200,
            pixel_height=100,
            used_on_pages=(0, 1),
        )
        dialog = ImageReplacementDialog((image,))
        qtbot.addWidget(dialog)

        assert dialog.selected_image == image
        assert "comparte" in dialog.warning_text
        assert "1, 2" in dialog.warning_text

    def test_el_dialogo_exige_una_imagen_de_reemplazo(self, qtbot: QtBot) -> None:
        image = EmbeddedImage(
            image_id="5",
            page_index=0,
            rect=PdfRect(72, 72, 272, 172),
        )
        dialog = ImageReplacementDialog((image,))
        qtbot.addWidget(dialog)
        accept = next(
            button for button in dialog.findChildren(QPushButton) if button.text() == "Reemplazar"
        )

        assert accept.isEnabled() is False

        dialog.set_replacement(
            LoadedImage(
                data=png_bytes(),
                mime_type="image/png",
                source_path=Path("reemplazo.png"),
                width=4,
                height=3,
            )
        )

        assert accept.isEnabled() is True
        assert dialog.replacement is not None

    def test_reemplazar_una_imagen_en_la_sesion(
        self,
        qtbot: QtBot,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        engine = FakePdfEngine(make_pages(2))
        window = build_window(qtbot, engine)
        open_ready(qtbot, window, tmp_path)
        image = EmbeddedImage(
            image_id="5",
            page_index=0,
            rect=PdfRect(72, 72, 272, 172),
            pixel_width=200,
            pixel_height=100,
        )
        engine.documents[0].page_images[0] = (image,)
        loaded = LoadedImage(
            data=png_bytes(),
            mime_type="image/png",
            source_path=tmp_path / "nueva.png",
            width=4,
            height=3,
        )

        class FakeDialog:
            def __init__(self, images: object, *_args: object, **_kwargs: object) -> None:
                assert images == (image,)

            def exec(self) -> int:
                return int(QDialog.DialogCode.Accepted)

            @property
            def selected_image(self) -> EmbeddedImage:
                return image

            @property
            def replacement(self) -> LoadedImage:
                return loaded

        monkeypatch.setattr(main_window_module, "ImageReplacementDialog", FakeDialog)

        window.replace_image_dialog()

        session = window.edit_session
        assert session is not None
        objects = session.objects
        assert len(objects) == 1
        obj = objects[0]
        assert isinstance(obj, ImageReplacementObject)
        assert obj.image_id == "5"
        assert obj.page_index == 0
        assert obj.data == loaded.data
        assert window.selected_object_id == obj.object_id
        assert window.is_dirty is True
        assert "reemplazar" in window.activity

        assert window.undo() is True
        assert session.objects == ()

    def test_sin_imagenes_avisa_al_usuario(
        self,
        qtbot: QtBot,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        engine = FakePdfEngine(make_pages(1))
        window = build_window(qtbot, engine)
        open_ready(qtbot, window, tmp_path)
        messages: list[str] = []
        monkeypatch.setattr(
            QMessageBox,
            "information",
            lambda _parent, _title, text, *_args: messages.append(text),
        )

        window.replace_image_dialog()

        assert len(messages) == 1
        assert "No se han detectado imágenes" in messages[0]
