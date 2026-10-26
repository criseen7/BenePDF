"""Pruebas del panel de propiedades del objeto seleccionado."""

from __future__ import annotations

from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot

from bene.domain.editing import ImageObject, RedactionObject, TextObject, TextStyle
from bene.domain.models import PdfRect
from bene.presentation.widgets.properties_panel import ObjectPropertiesPanel

pytestmark = pytest.mark.ui


def make_text() -> TextObject:
    return TextObject(
        object_id="texto-1",
        page_index=0,
        rect=PdfRect(10, 20, 210, 80),
        text="Hola mundo",
        style=TextStyle(font_size=16),
    )


def make_image() -> ImageObject:
    return ImageObject(
        object_id="imagen-1",
        page_index=0,
        rect=PdfRect(30, 40, 130, 140),
        data=b"png",
        mime_type="image/png",
        source_path=Path("foto.png"),
    )


def make_redaction() -> RedactionObject:
    return RedactionObject(
        object_id="redaccion-1",
        page_index=0,
        rect=PdfRect(10, 20, 210, 80),
    )


def test_sin_seleccion(qtbot: QtBot) -> None:
    panel = ObjectPropertiesPanel()
    qtbot.addWidget(panel)

    assert panel.object is None
    assert panel._apply.isEnabled() is False
    assert panel._x.isEnabled() is False


def test_muestra_el_texto_y_su_geometria(qtbot: QtBot) -> None:
    panel = ObjectPropertiesPanel()
    qtbot.addWidget(panel)

    panel.set_object(make_text())

    assert panel.object is not None
    assert panel._title.text() == "Texto añadido"
    assert panel._preview.text() == "Hola mundo"
    assert panel.object_geometry() == PdfRect(10, 20, 210, 80)
    assert panel._apply.isEnabled() is True


def test_muestra_el_archivo_de_la_imagen(qtbot: QtBot) -> None:
    panel = ObjectPropertiesPanel()
    qtbot.addWidget(panel)

    panel.set_object(make_image())

    assert panel._title.text() == "Imagen añadida"
    assert "foto.png" in panel._preview.text()


def test_muestra_la_redaccion_y_su_geometria(qtbot: QtBot) -> None:
    panel = ObjectPropertiesPanel()
    qtbot.addWidget(panel)

    panel.set_object(make_redaction())

    assert panel._title.text() == "Redacción"
    assert "eliminará de forma permanente" in panel._preview.text()
    assert panel.object_geometry() == PdfRect(10, 20, 210, 80)
    assert panel._apply.isEnabled() is True


def test_emite_la_geometria_editada(qtbot: QtBot) -> None:
    panel = ObjectPropertiesPanel()
    qtbot.addWidget(panel)
    panel.set_object(make_text())
    emitted: list[tuple[float, float, float, float]] = []
    panel.geometry_applied.connect(
        lambda x, y, width, height: emitted.append((x, y, width, height))
    )

    panel._x.setValue(50)
    panel._y.setValue(60)
    panel._width.setValue(120)
    panel._height.setValue(40)
    panel._apply.click()

    assert emitted == [(50.0, 60.0, 120.0, 40.0)]


def test_limpiar_la_seleccion(qtbot: QtBot) -> None:
    panel = ObjectPropertiesPanel()
    qtbot.addWidget(panel)
    panel.set_object(make_text())

    panel.set_object(None)

    assert panel.object is None
    assert panel._title.text() == "Sin selección"
    assert panel._apply.isEnabled() is False
