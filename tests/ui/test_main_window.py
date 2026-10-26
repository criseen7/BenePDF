"""Pruebas de la ventana principal con motor falso (RF-001 a RF-005, RF-017)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from PySide6.QtCore import QMimeData, QPointF, Qt, QUrl
from PySide6.QtGui import QAction, QDropEvent
from PySide6.QtWidgets import QInputDialog, QMessageBox, QSpinBox
from pytestqt.qtbot import QtBot

from bene.application.ports.pdf_engine import OpenedDocument, RenderedPage
from bene.application.use_cases.open_document import OpenDocument
from bene.application.use_cases.render_page import RenderPage
from bene.config import APP_NAME
from bene.domain.errors import EncryptedDocumentError, UnsupportedDocumentError
from bene.presentation.fit import FitMode
from bene.presentation.main_window import MainWindow
from bene.presentation.workers.render_worker import PageRenderer
from tests.unit.fakes import FakeDocument, FakePdfEngine, make_pages

pytestmark = pytest.mark.ui

RENDER_TIMEOUT_MS = 5000


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


@pytest.fixture
def engine() -> FakePdfEngine:
    return FakePdfEngine(make_pages(3))


@pytest.fixture
def window(qtbot: QtBot, engine: FakePdfEngine) -> MainWindow:
    return build_window(qtbot, engine)


def write_pdf(tmp_path: Path, name: str = "documento.pdf") -> Path:
    path = tmp_path / name
    path.write_bytes(b"%PDF-1.4\n")
    return path


def wait_ready(qtbot: QtBot, window: MainWindow) -> None:
    qtbot.waitUntil(
        lambda: window.canvas.has_image and window.activity == "Listo",
        timeout=RENDER_TIMEOUT_MS,
    )


def wait_page(qtbot: QtBot, window: MainWindow, page_index: int) -> None:
    qtbot.waitUntil(
        lambda: window.page_index == page_index and window.activity == "Listo",
        timeout=RENDER_TIMEOUT_MS,
    )


def open_ready(
    qtbot: QtBot, window: MainWindow, tmp_path: Path, name: str = "documento.pdf"
) -> Path:
    path = write_pdf(tmp_path, name)
    assert window.open_path(path) is True
    wait_ready(qtbot, window)
    return path


class TestEstadoInicial:
    def test_sin_documento(self, window: MainWindow) -> None:
        assert window.document_info is None
        assert window.page_index == 0
        assert window.fit_mode is FitMode.NONE
        assert window.canvas.has_image is False
        assert window.page_description == ""
        assert window.activity == ""
        assert window.windowTitle() == APP_NAME

    def test_las_acciones_de_documento_estan_desactivadas(self, window: MainWindow) -> None:
        acciones = {action.text(): action.isEnabled() for action in window.findChildren(QAction)}

        assert acciones["Cerrar documento"] is False
        assert acciones["Acercar"] is False
        assert acciones["Rotar vista 90°"] is False
        assert acciones["Abrir…"] is True

    def test_los_comandos_sin_documento_no_hacen_nada(self, window: MainWindow) -> None:
        window.go_to_page(2)
        window.previous_page()
        window.next_page()
        window.set_zoom(2.0)
        window.zoom_in()
        window.zoom_out()
        window.set_fit_mode(FitMode.WIDTH)
        window.rotate_view()

        assert window.document_info is None
        assert window.page_index == 0
        assert window.current_scale == 1.0
        assert window.view_rotation == 0


class TestApertura:
    def test_abre_y_muestra_la_primera_pagina(
        self, qtbot: QtBot, window: MainWindow, engine: FakePdfEngine, tmp_path: Path
    ) -> None:
        open_ready(qtbot, window, tmp_path)

        info = window.document_info
        assert info is not None
        assert info.page_count == 3
        assert info.title == "Documento de prueba"
        assert "Documento de prueba" in window.windowTitle()
        assert window.page_index == 0
        assert window.fit_mode is FitMode.PAGE
        assert 0.1 <= window.current_scale <= 8.0

        assert "Página 1 de 3" in window.page_description
        assert "texto seleccionable" in window.page_description
        assert "595 × 842 pt" in window.page_description
        assert window.canvas.image is not None
        assert engine.documents[0].render_calls[0][0] == 0

    def test_abrir_otro_documento_cierra_el_anterior(
        self, qtbot: QtBot, window: MainWindow, engine: FakePdfEngine, tmp_path: Path
    ) -> None:
        open_ready(qtbot, window, tmp_path, "primero.pdf")
        primero = engine.documents[0]

        open_ready(qtbot, window, tmp_path, "segundo.pdf")

        assert primero.closed is True
        assert len(engine.documents) == 2
        assert engine.documents[1].closed is False
        assert window.document_info is not None
        assert window.document_info.path.name == "segundo.pdf"

    def test_abre_con_una_ruta_como_texto(
        self, qtbot: QtBot, window: MainWindow, tmp_path: Path
    ) -> None:
        path = write_pdf(tmp_path, "texto.pdf")

        assert window.open_path(str(path)) is True
        wait_ready(qtbot, window)


class TestNavegacion:
    def test_avanza_y_retrocede(self, qtbot: QtBot, window: MainWindow, tmp_path: Path) -> None:
        open_ready(qtbot, window, tmp_path)

        window.next_page()
        wait_page(qtbot, window, 1)
        assert "Página 2 de 3" in window.page_description

        window.previous_page()
        wait_page(qtbot, window, 0)
        assert "Página 1 de 3" in window.page_description

    def test_no_sale_del_documento(self, qtbot: QtBot, window: MainWindow, tmp_path: Path) -> None:
        open_ready(qtbot, window, tmp_path)

        window.go_to_page(99)
        wait_page(qtbot, window, 2)
        window.next_page()
        assert window.page_index == 2

        window.go_to_page(-5)
        wait_page(qtbot, window, 0)
        window.previous_page()
        assert window.page_index == 0

    def test_el_selector_de_pagina_cambia_de_pagina(
        self, qtbot: QtBot, window: MainWindow, tmp_path: Path
    ) -> None:
        open_ready(qtbot, window, tmp_path)
        selector = window.findChild(QSpinBox)
        assert selector is not None

        selector.setValue(3)

        wait_page(qtbot, window, 2)


class TestZoom:
    def test_zoom_manual_y_pasos(self, qtbot: QtBot, window: MainWindow, tmp_path: Path) -> None:
        open_ready(qtbot, window, tmp_path)

        window.set_zoom(2.0)
        assert window.fit_mode is FitMode.NONE
        assert window.current_scale == pytest.approx(2.0)
        qtbot.waitUntil(lambda: window.activity == "Listo", timeout=RENDER_TIMEOUT_MS)
        image = window.canvas.image
        assert image is not None
        assert (image.width(), image.height()) == (1190, 1684)

        window.zoom_in()
        assert window.current_scale == pytest.approx(2.5)
        window.zoom_out()
        assert window.current_scale == pytest.approx(2.0)

    def test_limita_el_zoom_minimo(self, qtbot: QtBot, window: MainWindow, tmp_path: Path) -> None:
        open_ready(qtbot, window, tmp_path)

        window.set_zoom(0.01)

        assert window.current_scale == pytest.approx(0.1)
        qtbot.waitUntil(lambda: window.activity == "Listo", timeout=RENDER_TIMEOUT_MS)
        image = window.canvas.image
        assert image is not None
        assert image.width() < 100

    def test_ajustar_ancho_y_pagina(self, qtbot: QtBot, window: MainWindow, tmp_path: Path) -> None:
        # Una ventana ancha hace que el ajuste al ancho supere al de página, que
        # queda limitado por la altura disponible.
        window.resize(1600, 900)
        open_ready(qtbot, window, tmp_path)
        assert window.fit_mode is FitMode.PAGE
        escala_pagina = window.current_scale

        window.set_fit_mode(FitMode.WIDTH)

        assert window.fit_mode.value == FitMode.WIDTH.value
        assert window.current_scale > escala_pagina
        qtbot.waitUntil(lambda: window.activity == "Listo", timeout=RENDER_TIMEOUT_MS)

        window.set_fit_mode(FitMode.PAGE)
        assert window.fit_mode.value == FitMode.PAGE.value
        assert window.current_scale == pytest.approx(escala_pagina, rel=0.05)


class TestRotacion:
    def test_rota_la_vista_y_actualiza_la_imagen(
        self, qtbot: QtBot, window: MainWindow, tmp_path: Path
    ) -> None:
        open_ready(qtbot, window, tmp_path)

        window.rotate_view(90)

        assert window.view_rotation == 90
        qtbot.waitUntil(
            lambda: (
                window.activity == "Listo"
                and window.canvas.image is not None
                and window.canvas.image.width() > window.canvas.image.height()
            ),
            timeout=RENDER_TIMEOUT_MS,
        )

    def test_la_accion_de_rotar_gira_la_vista(
        self, qtbot: QtBot, window: MainWindow, tmp_path: Path
    ) -> None:
        open_ready(qtbot, window, tmp_path)
        action = next(
            action for action in window.findChildren(QAction) if action.text() == "Rotar vista 90°"
        )

        action.trigger()

        assert window.view_rotation == 90
        qtbot.waitUntil(lambda: window.activity == "Listo", timeout=RENDER_TIMEOUT_MS)

    def test_la_rotacion_es_modular(self, window: MainWindow, tmp_path: Path) -> None:
        assert window.open_path(write_pdf(tmp_path)) is True

        window.rotate_view(90)
        assert window.view_rotation == 90
        window.rotate_view(270)
        assert window.view_rotation == 0
        window.rotate_view(-90)
        assert window.view_rotation == 270


class TestHiDPI:
    def test_renderiza_a_la_densidad_de_la_pantalla(
        self,
        qtbot: QtBot,
        window: MainWindow,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(window, "_pixel_ratio", lambda: 2.0)

        open_ready(qtbot, window, tmp_path)

        image = window.canvas.image
        mapper = window.canvas.mapper
        assert image is not None
        assert mapper is not None
        assert image.devicePixelRatio() == pytest.approx(2.0)
        # El render se pidió al doble de resolución, pero el lienzo y el mapper
        # trabajan en píxeles lógicos.
        assert image.width() / (595 * mapper.scale) == pytest.approx(2.0, rel=0.01)
        assert window.canvas.width() == pytest.approx(595 * mapper.scale, rel=0.01)


class TestCierre:
    def test_cerrar_documento_libera_el_motor(
        self, qtbot: QtBot, window: MainWindow, engine: FakePdfEngine, tmp_path: Path
    ) -> None:
        open_ready(qtbot, window, tmp_path)
        document = engine.documents[0]

        window.close_document()

        assert document.closed is True
        assert window.document_info is None
        assert window.canvas.has_image is False
        assert window.page_description == ""
        assert window.activity == ""
        assert window.windowTitle() == APP_NAME

    def test_cerrar_la_ventana_libera_el_motor(
        self, qtbot: QtBot, window: MainWindow, engine: FakePdfEngine, tmp_path: Path
    ) -> None:
        open_ready(qtbot, window, tmp_path)
        document = engine.documents[0]

        window.close()

        assert document.closed is True


class TestErrores:
    def test_ruta_inexistente(
        self, window: MainWindow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        messages: list[str] = []
        monkeypatch.setattr(
            QMessageBox,
            "critical",
            lambda _parent, _title, text: messages.append(text),
        )

        assert window.open_path(tmp_path / "no-existe.pdf") is False

        assert len(messages) == 1
        assert "No existe el archivo" in messages[0]
        assert window.document_info is None

    def test_archivo_vacio(
        self, window: MainWindow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        messages: list[str] = []
        monkeypatch.setattr(
            QMessageBox,
            "critical",
            lambda _parent, _title, text: messages.append(text),
        )
        path = tmp_path / "vacio.pdf"
        path.write_bytes(b"")

        assert window.open_path(path) is False

        assert len(messages) == 1
        assert "no es un PDF válido" in messages[0]

    def test_error_previsto_del_motor(
        self, qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class BrokenEngine(FakePdfEngine):
            def open_document(self, path: Path, *, password: str | None = None) -> FakeDocument:
                raise UnsupportedDocumentError(path)

        messages: list[str] = []
        monkeypatch.setattr(
            QMessageBox,
            "critical",
            lambda _parent, _title, text: messages.append(text),
        )
        window = build_window(qtbot, BrokenEngine(make_pages(1)))

        assert window.open_path(write_pdf(tmp_path)) is False

        assert len(messages) == 1
        assert "no es un PDF válido" in messages[0]

    def test_error_inesperado(
        self, qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class ExplodingEngine(FakePdfEngine):
            def open_document(self, path: Path, *, password: str | None = None) -> FakeDocument:
                raise RuntimeError("fallo inesperado")

        messages: list[str] = []
        monkeypatch.setattr(
            QMessageBox,
            "critical",
            lambda _parent, _title, text: messages.append(text),
        )
        window = build_window(qtbot, ExplodingEngine(make_pages(1)))

        assert window.open_path(write_pdf(tmp_path)) is False

        assert len(messages) == 1
        assert "inesperado" in messages[0]

    def test_fallo_de_render(
        self, qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def renderer_factory(_document: OpenedDocument) -> PageRenderer:
            def renderer(page_index: int, *, scale: float, rotation: int = 0) -> RenderedPage:
                raise RuntimeError("no se pudo dibujar")

            return renderer

        warnings: list[str] = []
        monkeypatch.setattr(
            QMessageBox,
            "warning",
            lambda _parent, _title, text: warnings.append(text),
        )
        window = build_window(qtbot, FakePdfEngine(make_pages(1)), renderer_factory)

        assert window.open_path(write_pdf(tmp_path)) is True
        qtbot.waitUntil(
            lambda: window.activity == "No se pudo renderizar la página",
            timeout=RENDER_TIMEOUT_MS,
        )

        assert len(warnings) == 1
        assert "No se pudo renderizar" in warnings[0]
        assert window.canvas.has_image is False
        assert window.canvas.message == "No se pudo renderizar la página"


class TestCifrado:
    class EncryptedEngine(FakePdfEngine):
        def __init__(self) -> None:
            super().__init__(make_pages(2))
            self.passwords: list[str | None] = []

        def open_document(self, path: Path, *, password: str | None = None) -> FakeDocument:
            self.passwords.append(password)
            if password != "clave":
                raise EncryptedDocumentError(path, wrong_password=password is not None)
            return super().open_document(path, password=password)

    def test_pide_la_contrasena_y_abre(
        self, qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        engine = self.EncryptedEngine()
        window = build_window(qtbot, engine)
        monkeypatch.setattr(QInputDialog, "getText", lambda *_args, **_kwargs: ("clave", True))

        assert window.open_path(write_pdf(tmp_path, "cifrado.pdf")) is True
        wait_ready(qtbot, window)

        assert engine.passwords == [None, "clave"]
        assert window.document_info is not None

    def test_cancelar_la_contrasena(
        self, qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        engine = self.EncryptedEngine()
        window = build_window(qtbot, engine)
        monkeypatch.setattr(QInputDialog, "getText", lambda *_args, **_kwargs: ("", False))

        assert window.open_path(write_pdf(tmp_path, "cifrado.pdf")) is False

        assert engine.passwords == [None]
        assert window.document_info is None

    def test_limita_los_intentos(
        self, qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        engine = self.EncryptedEngine()
        window = build_window(qtbot, engine)
        prompts: list[tuple[object, ...]] = []
        messages: list[str] = []

        def ask(*args: object, **_kwargs: object) -> tuple[str, bool]:
            prompts.append(args)
            return ("mala", True)

        monkeypatch.setattr(QInputDialog, "getText", ask)
        monkeypatch.setattr(
            QMessageBox,
            "critical",
            lambda _parent, _title, text: messages.append(text),
        )

        assert window.open_path(write_pdf(tmp_path, "cifrado.pdf")) is False

        assert len(prompts) == 3
        assert engine.passwords == [None, "mala", "mala", "mala"]
        assert len(messages) == 1
        assert "contraseña no es correcta" in messages[0]


class TestArrastrarYSoltar:
    def test_extrae_el_archivo_local(self, tmp_path: Path) -> None:
        path = tmp_path / "documento.pdf"
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(path))])
        event = QDropEvent(
            QPointF(10, 10),
            Qt.DropAction.CopyAction,
            mime,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )

        assert MainWindow._first_local_file(event) == path

    def test_ignora_urls_remotas(self) -> None:
        mime = QMimeData()
        mime.setUrls([QUrl("https://example.com/documento.pdf")])
        event = QDropEvent(
            QPointF(10, 10),
            Qt.DropAction.CopyAction,
            mime,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )

        assert MainWindow._first_local_file(event) is None

    def test_ignora_lo_que_no_son_urls(self) -> None:
        mime = QMimeData()
        mime.setText("solo texto")
        event = QDropEvent(
            QPointF(10, 10),
            Qt.DropAction.CopyAction,
            mime,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )

        assert MainWindow._first_local_file(event) is None

    def test_soltar_un_pdf_lo_abre(self, qtbot: QtBot, window: MainWindow, tmp_path: Path) -> None:
        path = write_pdf(tmp_path)
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(path))])
        event = QDropEvent(
            QPointF(10, 10),
            Qt.DropAction.CopyAction,
            mime,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )

        window.dropEvent(event)

        assert window.document_info is not None
        wait_ready(qtbot, window)
