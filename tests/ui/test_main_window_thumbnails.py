"""Pruebas de la integración de miniaturas en la ventana principal."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

from bene.application.ports.pdf_engine import OpenedDocument
from bene.application.use_cases.open_document import OpenDocument
from bene.application.use_cases.render_page import RenderPage
from bene.presentation.main_window import MainWindow
from bene.presentation.widgets.thumbnail_panel import ThumbnailPanel
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


def open_ready(qtbot: QtBot, window: MainWindow, tmp_path: Path) -> ThumbnailPanel:
    path = write_pdf(tmp_path)
    assert window.open_path(path) is True
    qtbot.waitUntil(
        lambda: window.canvas.has_image and window.activity == "Listo",
        timeout=TIMEOUT_MS,
    )
    panel = window.findChild(ThumbnailPanel)
    assert panel is not None
    return panel


def wait_thumbnails(qtbot: QtBot, panel: ThumbnailPanel, count: int) -> None:
    qtbot.waitUntil(
        lambda: all(not panel.thumbnail(index).isNull() for index in range(count)),
        timeout=TIMEOUT_MS,
    )


def test_crea_una_miniatura_por_pagina(qtbot: QtBot, tmp_path: Path) -> None:
    window = build_window(qtbot, FakePdfEngine(make_pages(3)))

    panel = open_ready(qtbot, window, tmp_path)

    assert panel.page_count == 3
    wait_thumbnails(qtbot, panel, 3)


def test_marca_la_pagina_actual(qtbot: QtBot, tmp_path: Path) -> None:
    window = build_window(qtbot, FakePdfEngine(make_pages(3)))
    panel = open_ready(qtbot, window, tmp_path)

    window.go_to_page(1)

    assert panel.currentRow() == 1


def test_el_clic_en_una_miniatura_navega(qtbot: QtBot, tmp_path: Path) -> None:
    window = build_window(qtbot, FakePdfEngine(make_pages(3)))
    panel = open_ready(qtbot, window, tmp_path)
    wait_thumbnails(qtbot, panel, 3)
    item = panel.item(2)
    assert item is not None

    rect = panel.visualItemRect(item)
    qtbot.mouseClick(panel.viewport(), Qt.MouseButton.LeftButton, pos=rect.center())

    qtbot.waitUntil(
        lambda: window.page_index == 2 and window.activity == "Listo",
        timeout=TIMEOUT_MS,
    )


def test_cerrar_el_documento_limpia_las_miniaturas(qtbot: QtBot, tmp_path: Path) -> None:
    window = build_window(qtbot, FakePdfEngine(make_pages(2)))
    panel = open_ready(qtbot, window, tmp_path)
    wait_thumbnails(qtbot, panel, 2)

    window.close_document()

    assert panel.page_count == 0
