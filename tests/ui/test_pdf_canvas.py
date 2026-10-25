"""Pruebas de interfaz: conversión a imagen y lienzo del visor."""

from __future__ import annotations

from typing import cast

import pytest
from PySide6.QtCore import QSize
from PySide6.QtGui import QColor, QImage
from pytestqt.qtbot import QtBot

from bene.application.ports.pdf_engine import RenderedPage
from bene.presentation.viewer.pdf_canvas import (
    BACKGROUND,
    PLACEHOLDER_MESSAGE,
    PLACEHOLDER_SIZE,
    PdfCanvas,
    rendered_page_to_image,
)

pytestmark = pytest.mark.ui


def make_red_render(width: int = 2, height: int = 2) -> tuple[RenderedPage, bytearray]:
    stride = width * 3
    samples = bytearray(b"\xff\x00\x00" * (width * height))
    render = RenderedPage(
        page_index=0,
        width=width,
        height=height,
        stride=stride,
        samples=cast(bytes, samples),
        scale=1.0,
    )
    return render, samples


def make_image(width: int = 20, height: int = 10) -> QImage:
    image = QImage(width, height, QImage.Format.Format_RGB888)
    image.fill(QColor("#ff0000"))
    return image


def test_convierte_el_render_en_imagen() -> None:
    render, _ = make_red_render(width=4, height=3)

    image = rendered_page_to_image(render)

    assert image.width() == 4
    assert image.height() == 3
    assert image.format() == QImage.Format.Format_RGB888
    assert image.pixelColor(1, 1) == QColor("#ff0000")


def test_la_imagen_copia_los_pixeles() -> None:
    render, samples = make_red_render()

    image = rendered_page_to_image(render)
    samples[:] = b"\x00\x00\x00" * (len(samples) // 3)

    assert image.pixelColor(0, 0) == QColor("#ff0000")


def test_lienzo_sin_imagen(qtbot: QtBot) -> None:
    canvas = PdfCanvas()
    qtbot.addWidget(canvas)

    assert canvas.image is None
    assert canvas.has_image is False
    assert canvas.message == PLACEHOLDER_MESSAGE
    assert canvas.size() == PLACEHOLDER_SIZE


def test_lienzo_muestra_la_imagen(qtbot: QtBot) -> None:
    canvas = PdfCanvas()
    qtbot.addWidget(canvas)
    image = make_image(120, 80)

    canvas.set_image(image)

    assert canvas.has_image is True
    assert canvas.image is image
    assert canvas.size() == QSize(120, 80)


def test_lienzo_vuelve_al_marcador(qtbot: QtBot) -> None:
    canvas = PdfCanvas()
    qtbot.addWidget(canvas)
    canvas.set_image(make_image())

    canvas.set_image(None)

    assert canvas.image is None
    assert canvas.size() == PLACEHOLDER_SIZE


def test_lienzo_cambia_el_mensaje(qtbot: QtBot) -> None:
    canvas = PdfCanvas()
    qtbot.addWidget(canvas)

    canvas.set_message("Renderizando página…")

    assert canvas.message == "Renderizando página…"


def test_lienzo_pinta_la_imagen(qtbot: QtBot) -> None:
    canvas = PdfCanvas()
    qtbot.addWidget(canvas)
    canvas.set_image(make_image(40, 30))

    pixmap = canvas.grab()

    assert pixmap.width() == 40
    assert pixmap.toImage().pixelColor(5, 5) == QColor("#ff0000")


def test_lienzo_pinta_el_fondo_sin_imagen(qtbot: QtBot) -> None:
    canvas = PdfCanvas()
    qtbot.addWidget(canvas)

    pixmap = canvas.grab()

    assert pixmap.toImage().pixelColor(2, 2) == BACKGROUND
