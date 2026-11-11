"""Pruebas de accesibilidad de la interfaz (RNF-011).

Cubren nombres accesibles, etiquetas asociadas y orden de tabulación de los
controles que se usan con el teclado. No sustituyen a una revisión visual con
un lector de pantalla, pero evitan las regresiones más habituales.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QWidget
from pytestqt.qtbot import QtBot

from bene.application.ports.pdf_engine import OpenedDocument
from bene.application.use_cases.open_document import OpenDocument
from bene.application.use_cases.render_page import RenderPage
from bene.config import APP_NAME
from bene.presentation.dialogs.text_dialog import TextDialog
from bene.presentation.main_window import MainWindow
from bene.presentation.widgets.properties_panel import ObjectPropertiesPanel
from bene.presentation.widgets.thumbnail_panel import ThumbnailPanel
from bene.presentation.workers.render_worker import PageRenderer
from tests.unit.fakes import FakePdfEngine, make_pages

pytestmark = pytest.mark.ui

TIMEOUT_MS = 5000


def focus_chain(widget: QWidget) -> list[QWidget]:
    """Recorre la cadena de foco hasta volver al punto de partida."""
    chain: list[QWidget] = []
    current: QWidget = widget
    for _ in range(300):
        chain.append(current)
        next_widget = current.nextInFocusChain()
        if next_widget is None or next_widget is widget:
            break
        current = next_widget
    return chain


def assert_ordered(chain: list[QWidget], *widgets: QWidget) -> None:
    """Comprueba el orden relativo; Qt intercala los editores internos de los spin."""
    positions = [chain.index(widget) for widget in widgets]
    assert positions == sorted(positions)
    assert len(set(positions)) == len(positions)


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


def open_ready(qtbot: QtBot, window: MainWindow, tmp_path: Path) -> None:
    path = tmp_path / "documento.pdf"
    path.write_bytes(b"%PDF-1.4\n")
    assert window.open_path(path) is True
    qtbot.waitUntil(
        lambda: window.canvas.has_image and window.activity == "Listo",
        timeout=TIMEOUT_MS,
    )


class TestVentanaPrincipal:
    def test_la_ventana_y_el_lienzo_se_anuncian(self, qtbot: QtBot, tmp_path: Path) -> None:
        window = build_window(qtbot, FakePdfEngine(make_pages(2)))

        assert window.accessibleName() == APP_NAME
        assert window.accessibleDescription()
        assert window.canvas.accessibleName()
        assert window.canvas.accessibleDescription()

        open_ready(qtbot, window, tmp_path)

        assert "Página 1 de 2" in window.canvas.accessibleDescription()

    def test_la_navegacion_tiene_nombres_y_etiquetas(self, qtbot: QtBot, tmp_path: Path) -> None:
        window = build_window(qtbot, FakePdfEngine(make_pages(2)))
        open_ready(qtbot, window, tmp_path)

        assert window._previous_button.accessibleName() == "Página anterior"
        assert window._next_button.accessibleName() == "Página siguiente"
        assert window._page_spin.accessibleName() == "Número de página"
        assert window._page_spin.accessibleDescription()
        assert window._thumbnails.accessibleName() == "Miniaturas de páginas"

    def test_los_controles_de_dibujo_se_anuncian(self, qtbot: QtBot, tmp_path: Path) -> None:
        window = build_window(qtbot, FakePdfEngine(make_pages(1)))
        open_ready(qtbot, window, tmp_path)

        assert window.draw_action.text() == "Dibujar"
        assert window.draw_action.objectName() == "accion_dibujar"
        assert window.stroke_width_spin.accessibleName() == "Grosor del trazo"
        assert window.stroke_width_spin.accessibleDescription()
        assert window.stroke_color_button.accessibleName() == "Color del trazo"
        assert window.stroke_color_button.accessibleDescription()

    def test_el_orden_de_tabulacion_sigue_la_navegacion(self, qtbot: QtBot, tmp_path: Path) -> None:
        window = build_window(qtbot, FakePdfEngine(make_pages(2)))
        open_ready(qtbot, window, tmp_path)

        chain = focus_chain(window._previous_button)
        assert_ordered(
            chain,
            window._previous_button,
            window._page_spin,
            window._next_button,
            window._thumbnails,
            window.canvas,
        )
        assert window.canvas.focusPolicy() == Qt.FocusPolicy.StrongFocus

    def test_las_miniaturas_anuncian_su_pagina(self, qtbot: QtBot) -> None:
        panel = ThumbnailPanel()
        qtbot.addWidget(panel)
        panel.set_page_count(3)

        texts = [
            panel.item(index).data(Qt.ItemDataRole.AccessibleTextRole)
            for index in range(panel.page_count)
        ]
        assert texts == ["Página 1", "Página 2", "Página 3"]
        assert panel.item(0).toolTip() == "Ir a la página 1"


class TestDialogoDeTexto:
    def test_los_campos_tienen_nombre_y_etiqueta(self, qtbot: QtBot) -> None:
        dialog = TextDialog(text="Hola")
        qtbot.addWidget(dialog)

        assert dialog.accessibleName()
        assert dialog._text.accessibleName() == "Texto"
        assert dialog._font.accessibleName() == "Fuente"
        assert dialog._size.accessibleName() == "Tamaño"
        assert dialog._color_button.accessibleName() == "Color"
        assert dialog._alignment.accessibleName() == "Alineación"

        label = dialog.findChild(QLabel, "etiqueta_texto")
        assert label is not None
        assert label.buddy() is dialog._text

    def test_el_orden_de_tabulacion_empieza_en_el_texto(self, qtbot: QtBot) -> None:
        dialog = TextDialog()
        qtbot.addWidget(dialog)

        chain = focus_chain(dialog._text)
        assert_ordered(
            chain,
            dialog._text,
            dialog._font,
            dialog._size,
            dialog._color_button,
            dialog._alignment,
        )


class TestPanelDePropiedades:
    def test_los_campos_y_el_boton_se_anuncian(self, qtbot: QtBot) -> None:
        panel = ObjectPropertiesPanel()
        qtbot.addWidget(panel)

        assert panel.accessibleName()
        assert panel._x.accessibleName() == "Coordenada X"
        assert panel._y.accessibleName() == "Coordenada Y"
        assert panel._width.accessibleName() == "Ancho"
        assert panel._height.accessibleName() == "Alto"
        assert panel._apply.accessibleName() == "Aplicar cambios"
        assert panel._title.accessibleName() == "Objeto seleccionado"

    def test_el_orden_de_tabulacion_recorre_la_geometria(self, qtbot: QtBot) -> None:
        panel = ObjectPropertiesPanel()
        qtbot.addWidget(panel)

        chain = focus_chain(panel._x)
        assert_ordered(chain, panel._x, panel._y, panel._width, panel._height, panel._apply)
