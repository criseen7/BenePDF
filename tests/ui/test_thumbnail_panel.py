"""Pruebas del panel lateral de miniaturas."""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage
from pytestqt.qtbot import QtBot

from bene.presentation.widgets.thumbnail_panel import ThumbnailPanel

pytestmark = pytest.mark.ui


def make_image(width: int = 10, height: int = 14, color: str = "#ff0000") -> QImage:
    image = QImage(width, height, QImage.Format.Format_RGB888)
    image.fill(QColor(color))
    return image


def test_crea_una_entrada_por_pagina(qtbot: QtBot) -> None:
    panel = ThumbnailPanel()
    qtbot.addWidget(panel)

    panel.set_page_count(4)

    assert panel.page_count == 4
    assert [panel.item(i).text() for i in range(4)] == ["1", "2", "3", "4"]


def test_asigna_la_miniatura(qtbot: QtBot) -> None:
    panel = ThumbnailPanel()
    qtbot.addWidget(panel)
    panel.set_page_count(2)

    panel.set_thumbnail(1, make_image())

    assert panel.thumbnail(0).isNull()
    assert not panel.thumbnail(1).isNull()


def test_marca_la_pagina_actual(qtbot: QtBot) -> None:
    panel = ThumbnailPanel()
    qtbot.addWidget(panel)
    panel.set_page_count(3)

    panel.set_current_page(2)

    assert panel.currentRow() == 2


def test_el_clic_emite_la_pagina(qtbot: QtBot) -> None:
    panel = ThumbnailPanel()
    qtbot.addWidget(panel)
    panel.set_page_count(3)
    panel.resize(200, 500)
    panel.show()
    activated: list[int] = []
    panel.page_activated.connect(activated.append)
    item = panel.item(1)
    assert item is not None

    rect = panel.visualItemRect(item)
    qtbot.mouseClick(panel.viewport(), Qt.MouseButton.LeftButton, pos=rect.center())

    assert activated == [1]


def test_limpiar_el_panel(qtbot: QtBot) -> None:
    panel = ThumbnailPanel()
    qtbot.addWidget(panel)
    panel.set_page_count(3)
    panel.set_thumbnail(0, make_image())

    panel.set_page_count(0)

    assert panel.page_count == 0
    assert panel.currentRow() == -1
