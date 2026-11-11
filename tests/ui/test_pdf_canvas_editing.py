"""Pruebas de selección, colocación y transformación en el lienzo."""

from __future__ import annotations

import pytest
from PySide6.QtCore import QBuffer, QByteArray, QEvent, QIODevice, QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QImage, QImageWriter, QMouseEvent
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from bene.domain.editing import (
    ImageObject,
    RedactionObject,
    StrokeObject,
    StrokeStyle,
    TextObject,
)
from bene.domain.models import PdfRect
from bene.presentation.viewer.coordinates import CoordinateMapper
from bene.presentation.viewer.pdf_canvas import CanvasTool, PdfCanvas

pytestmark = pytest.mark.ui


def make_canvas(
    qtbot: QtBot,
    *,
    page_width: float = 200.0,
    page_height: float = 100.0,
    rotation: int = 0,
    background: str = "#ffffff",
) -> PdfCanvas:
    mapper = CoordinateMapper(page_width, page_height, scale=1.0, view_rotation=rotation)
    image = QImage(round(mapper.view_width), round(mapper.view_height), QImage.Format.Format_RGB888)
    image.fill(QColor(background))
    canvas = PdfCanvas()
    qtbot.addWidget(canvas)
    canvas.set_image(image)
    canvas.set_mapper(mapper)
    canvas.show()
    return canvas


def send_mouse_move(
    widget: PdfCanvas,
    position: QPoint,
    modifiers: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier,
) -> None:
    """Envía un movimiento con modificadores; ``qtbot.mouseMove`` no los admite."""
    event = QMouseEvent(
        QEvent.Type.MouseMove,
        QPointF(position),
        QPointF(widget.mapToGlobal(position)),
        Qt.MouseButton.NoButton,
        Qt.MouseButton.LeftButton,
        modifiers,
    )
    QApplication.sendEvent(widget, event)


def make_text(rect: PdfRect | None = None, text: str = "Hola") -> TextObject:
    return TextObject(
        object_id="texto-1",
        page_index=0,
        rect=rect if rect is not None else PdfRect(10, 20, 60, 80),
        text=text,
    )


def png_bytes() -> bytes:
    image = QImage(2, 2, QImage.Format.Format_RGB888)
    image.fill(QColor("#ff0000"))
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    writer = QImageWriter(buffer, b"PNG")
    assert writer.write(image)
    buffer.close()
    return bytes(data.data())


def make_image(rect: PdfRect | None = None) -> ImageObject:
    return ImageObject(
        object_id="imagen-1",
        page_index=0,
        rect=rect if rect is not None else PdfRect(70, 10, 110, 50),
        data=png_bytes(),
        mime_type="image/png",
    )


class TestRegion:
    def test_selecciona_una_region_y_la_convierte(self, qtbot: QtBot) -> None:
        canvas = make_canvas(qtbot)
        canvas.set_tool(CanvasTool.REGION)
        regions: list[PdfRect] = []
        canvas.region_selected.connect(regions.append)

        qtbot.mousePress(canvas, Qt.MouseButton.LeftButton, pos=QPoint(10, 20))
        qtbot.mouseMove(canvas, QPoint(60, 80))
        qtbot.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=QPoint(60, 80))

        assert regions == [PdfRect(10, 20, 60, 80)]
        assert canvas.region == PdfRect(10, 20, 60, 80)

    def test_region_con_rotacion_de_vista(self, qtbot: QtBot) -> None:
        canvas = make_canvas(qtbot, rotation=90)
        canvas.set_tool(CanvasTool.REGION)
        regions: list[PdfRect] = []
        canvas.region_selected.connect(regions.append)

        qtbot.mousePress(canvas, Qt.MouseButton.LeftButton, pos=QPoint(10, 20))
        qtbot.mouseMove(canvas, QPoint(60, 80))
        qtbot.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=QPoint(60, 80))

        assert regions == [PdfRect(20, 40, 80, 90)]

    def test_un_clic_sin_arrastre_no_crea_region(self, qtbot: QtBot) -> None:
        canvas = make_canvas(qtbot)
        canvas.set_tool(CanvasTool.REGION)
        regions: list[PdfRect] = []
        canvas.region_selected.connect(regions.append)

        qtbot.mousePress(canvas, Qt.MouseButton.LeftButton, pos=QPoint(10, 20))
        qtbot.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=QPoint(10, 20))

        assert regions == []
        assert canvas.region is None

    def test_clear_region(self, qtbot: QtBot) -> None:
        canvas = make_canvas(qtbot)
        canvas.set_region(PdfRect(10, 20, 60, 80))

        canvas.clear_region()

        assert canvas.region is None


class TestRedaccion:
    def test_arrastrar_emite_la_region_a_redactar(self, qtbot: QtBot) -> None:
        canvas = make_canvas(qtbot)
        canvas.set_tool(CanvasTool.REDACT)
        redactions: list[PdfRect] = []
        regions: list[PdfRect] = []
        canvas.redaction_requested.connect(redactions.append)
        canvas.region_selected.connect(regions.append)

        qtbot.mousePress(canvas, Qt.MouseButton.LeftButton, pos=QPoint(10, 20))
        qtbot.mouseMove(canvas, QPoint(60, 80))
        qtbot.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=QPoint(60, 80))

        assert redactions == [PdfRect(10, 20, 60, 80)]
        assert regions == []
        assert canvas.region is None

    def test_un_clic_sin_arrastre_no_marca_redaccion(self, qtbot: QtBot) -> None:
        canvas = make_canvas(qtbot)
        canvas.set_tool(CanvasTool.REDACT)
        redactions: list[PdfRect] = []
        canvas.redaction_requested.connect(redactions.append)

        qtbot.mousePress(canvas, Qt.MouseButton.LeftButton, pos=QPoint(10, 20))
        qtbot.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=QPoint(10, 20))

        assert redactions == []

    def test_pinta_la_redaccion_en_negro(self, qtbot: QtBot) -> None:
        canvas = make_canvas(qtbot)
        canvas.set_objects(
            [
                RedactionObject(
                    object_id="redaccion-1",
                    page_index=0,
                    rect=PdfRect(10, 20, 60, 80),
                )
            ]
        )

        image = canvas.grab().toImage()

        assert image.pixelColor(35, 50).lightness() < 100
        assert image.pixelColor(150, 20).lightness() > 200


class TestColocacion:
    def test_emite_el_punto_en_puntos_pdf(self, qtbot: QtBot) -> None:
        canvas = make_canvas(qtbot)
        canvas.set_tool(CanvasTool.PLACE)
        points: list[tuple[float, float]] = []
        canvas.placement_requested.connect(lambda x, y: points.append((x, y)))

        qtbot.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=QPoint(25, 35))

        assert points == [(25.0, 35.0)]

    def test_el_punto_se_limita_a_la_pagina(self, qtbot: QtBot) -> None:
        canvas = make_canvas(qtbot)
        canvas.set_tool(CanvasTool.PLACE)
        points: list[tuple[float, float]] = []
        canvas.placement_requested.connect(lambda x, y: points.append((x, y)))

        qtbot.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=QPoint(250, 150))

        assert points == [(200.0, 100.0)]


class TestDibujo:
    def test_el_trazo_emite_puntos_y_estilo(self, qtbot: QtBot) -> None:
        canvas = make_canvas(qtbot)
        canvas.set_tool(CanvasTool.DRAW)
        style = StrokeStyle(color="#ff0000", width=4.0)
        canvas.set_stroke_style(style)
        strokes: list[tuple[tuple[tuple[float, float], ...], StrokeStyle]] = []
        canvas.stroke_requested.connect(
            lambda points, stroke_style: strokes.append((points, stroke_style))
        )

        qtbot.mousePress(canvas, Qt.MouseButton.LeftButton, pos=QPoint(10, 20))
        qtbot.mouseMove(canvas, QPoint(60, 40))
        qtbot.mouseMove(canvas, QPoint(80, 60))
        qtbot.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=QPoint(80, 60))

        assert strokes == [(((10.0, 20.0), (60.0, 40.0), (80.0, 60.0)), style)]

    def test_un_clic_crea_un_punto(self, qtbot: QtBot) -> None:
        canvas = make_canvas(qtbot)
        canvas.set_tool(CanvasTool.DRAW)
        strokes: list[object] = []
        canvas.stroke_requested.connect(lambda points, _style: strokes.append(points))

        qtbot.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=QPoint(25, 35))

        assert strokes == [((25.0, 35.0),)]

    def test_el_trazo_respeta_la_rotacion_de_vista(self, qtbot: QtBot) -> None:
        canvas = make_canvas(qtbot, rotation=90)
        canvas.set_tool(CanvasTool.DRAW)
        mapper = canvas.mapper
        assert mapper is not None
        strokes: list[object] = []
        canvas.stroke_requested.connect(lambda points, _style: strokes.append(points))

        qtbot.mousePress(canvas, Qt.MouseButton.LeftButton, pos=QPoint(10, 20))
        qtbot.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=QPoint(10, 20))

        assert strokes == [(mapper.to_page_clamped(10, 20),)]

    def test_la_vista_previa_se_pinta_y_desaparece(self, qtbot: QtBot) -> None:
        canvas = make_canvas(qtbot)
        canvas.set_tool(CanvasTool.DRAW)
        canvas.set_stroke_style(StrokeStyle(color="#ff0000", width=6.0))

        qtbot.mousePress(canvas, Qt.MouseButton.LeftButton, pos=QPoint(10, 20))
        qtbot.mouseMove(canvas, QPoint(80, 20))
        preview = canvas.grab().toImage().pixelColor(45, 20)
        assert preview.red() > 150 and preview.green() < 100

        qtbot.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=QPoint(80, 20))
        after = canvas.grab().toImage().pixelColor(45, 20)
        assert after.red() > 200 and after.green() > 200 and after.blue() > 200

    def test_pinta_un_trazo_guardado(self, qtbot: QtBot) -> None:
        canvas = make_canvas(qtbot)
        canvas.set_objects(
            [
                StrokeObject(
                    object_id="trazo-1",
                    page_index=0,
                    points=((10.0, 20.0), (80.0, 20.0)),
                    style=StrokeStyle(color="#0000ff", width=6.0),
                )
            ]
        )

        image = canvas.grab().toImage()

        color = image.pixelColor(45, 20)
        assert color.blue() > 150 and color.red() < 100


class TestSeleccion:
    def test_selecciona_un_objeto_y_lo_deselecciona(self, qtbot: QtBot) -> None:
        canvas = make_canvas(qtbot)
        text = make_text()
        canvas.set_objects([text])
        selected: list[object] = []
        canvas.selection_changed.connect(selected.append)

        qtbot.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=QPoint(30, 40))
        assert canvas.selected_object_id == "texto-1"
        assert selected == ["texto-1"]

        qtbot.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=QPoint(150, 90))
        assert canvas.selected_object_id is None
        assert selected == ["texto-1", None]

    def test_si_desaparece_el_objeto_se_limpia_la_seleccion(self, qtbot: QtBot) -> None:
        canvas = make_canvas(qtbot)
        canvas.set_objects([make_text()])
        canvas.select_object("texto-1")

        canvas.set_objects([])

        assert canvas.selected_object_id is None

    def test_selecciona_una_imagen(self, qtbot: QtBot) -> None:
        canvas = make_canvas(qtbot)
        canvas.set_objects([make_image()])

        qtbot.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=QPoint(90, 30))

        assert canvas.selected_object_id == "imagen-1"


class TestTransformaciones:
    def test_arrastra_para_mover(self, qtbot: QtBot) -> None:
        canvas = make_canvas(qtbot)
        canvas.set_objects([make_text()])
        canvas.select_object("texto-1")
        requests: list[tuple[str, PdfRect]] = []
        canvas.transform_requested.connect(lambda oid, rect: requests.append((oid, rect)))

        qtbot.mousePress(canvas, Qt.MouseButton.LeftButton, pos=QPoint(30, 40))
        qtbot.mouseMove(canvas, QPoint(50, 50))
        qtbot.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=QPoint(50, 50))

        assert requests == [("texto-1", PdfRect(30, 30, 80, 90))]

    def test_no_emite_si_no_hay_desplazamiento(self, qtbot: QtBot) -> None:
        canvas = make_canvas(qtbot)
        canvas.set_objects([make_text()])
        canvas.select_object("texto-1")
        requests: list[tuple[str, PdfRect]] = []
        canvas.transform_requested.connect(lambda oid, rect: requests.append((oid, rect)))

        qtbot.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=QPoint(30, 40))

        assert requests == []

    def test_redimensiona_desde_la_esquina_inferior_derecha(self, qtbot: QtBot) -> None:
        canvas = make_canvas(qtbot)
        canvas.set_objects([make_text()])
        canvas.select_object("texto-1")
        requests: list[tuple[str, PdfRect]] = []
        canvas.transform_requested.connect(lambda oid, rect: requests.append((oid, rect)))

        qtbot.mousePress(canvas, Qt.MouseButton.LeftButton, pos=QPoint(60, 80))
        qtbot.mouseMove(canvas, QPoint(100, 90))
        qtbot.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=QPoint(100, 90))

        assert requests == [("texto-1", PdfRect(10, 20, 100, 90))]

    def test_arrastrar_el_cuerpo_cerca_de_una_esquina_no_redimensiona(self, qtbot: QtBot) -> None:
        """Arrastrar dentro del objeto siempre mueve, aunque se coja cerca del asa."""
        canvas = make_canvas(qtbot)
        canvas.set_objects([make_text()])
        canvas.select_object("texto-1")
        requests: list[tuple[str, PdfRect]] = []
        canvas.transform_requested.connect(lambda oid, rect: requests.append((oid, rect)))

        # (52, 72) está dentro del objeto y a 8 px de la esquina (60, 80),
        # fuera del asa visible.
        qtbot.mousePress(canvas, Qt.MouseButton.LeftButton, pos=QPoint(52, 72))
        qtbot.mouseMove(canvas, QPoint(72, 82))
        qtbot.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=QPoint(72, 82))

        assert requests == [("texto-1", PdfRect(30, 30, 80, 90))]

    def test_las_asas_solo_actuan_con_el_objeto_seleccionado(self, qtbot: QtBot) -> None:
        canvas = make_canvas(qtbot)
        canvas.set_objects([make_text()])
        requests: list[tuple[str, PdfRect]] = []
        canvas.transform_requested.connect(lambda oid, rect: requests.append((oid, rect)))

        # Primer clic en la esquina: solo selecciona.
        qtbot.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=QPoint(60, 80))
        assert canvas.selected_object_id == "texto-1"
        assert requests == []

        # Con el objeto ya seleccionado, el asa sí redimensiona.
        qtbot.mousePress(canvas, Qt.MouseButton.LeftButton, pos=QPoint(60, 80))
        qtbot.mouseMove(canvas, QPoint(100, 90))
        qtbot.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=QPoint(100, 90))

        assert requests == [("texto-1", PdfRect(10, 20, 100, 90))]

    def test_el_cursor_indica_redimensionado_solo_al_objeto_seleccionado(
        self, qtbot: QtBot
    ) -> None:
        canvas = make_canvas(qtbot)
        canvas.set_objects([make_text()])

        # Sin seleccionar, incluso sobre una esquina, se puede mover.
        qtbot.mouseMove(canvas, QPoint(60, 20))
        assert canvas.cursor().shape() is Qt.CursorShape.SizeAllCursor

        canvas.select_object("texto-1")
        qtbot.mouseMove(canvas, QPoint(10, 20))
        assert canvas.cursor().shape() is Qt.CursorShape.SizeFDiagCursor

        qtbot.mouseMove(canvas, QPoint(60, 20))
        assert canvas.cursor().shape() is Qt.CursorShape.SizeBDiagCursor

        qtbot.mouseMove(canvas, QPoint(30, 40))
        assert canvas.cursor().shape() is Qt.CursorShape.SizeAllCursor

        qtbot.mouseMove(canvas, QPoint(150, 90))
        assert canvas.cursor().shape() is Qt.CursorShape.ArrowCursor

    def test_redimensiona_con_rotacion(self, qtbot: QtBot) -> None:
        canvas = make_canvas(qtbot, rotation=90)
        canvas.set_objects([make_text()])
        canvas.select_object("texto-1")
        requests: list[tuple[str, PdfRect]] = []
        canvas.transform_requested.connect(lambda oid, rect: requests.append((oid, rect)))

        # La esquina PDF (60, 80) se ve en (20, 60) con rotación de 90 grados.
        qtbot.mousePress(canvas, Qt.MouseButton.LeftButton, pos=QPoint(20, 60))
        qtbot.mouseMove(canvas, QPoint(10, 90))
        qtbot.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=QPoint(10, 90))

        assert requests == [("texto-1", PdfRect(10, 20, 90, 90))]

    def test_las_asas_siguen_al_preview_durante_el_arrastre(self, qtbot: QtBot) -> None:
        canvas = make_canvas(qtbot, background="#e8e8e8")
        canvas.set_objects([make_text()])
        canvas.select_object("texto-1")

        qtbot.mousePress(canvas, Qt.MouseButton.LeftButton, pos=QPoint(60, 80))
        qtbot.mouseMove(canvas, QPoint(100, 90))

        image = QImage(canvas.size(), QImage.Format.Format_RGB888)
        image.fill(QColor("#000000"))
        canvas.render(image)

        # El asa inferior derecha se dibuja en la esquina nueva del preview.
        assert image.pixelColor(100, 90).lightness() > 240
        # La esquina antigua ya no conserva un asa blanca.
        assert image.pixelColor(60, 80).lightness() < 240

    def test_shift_conserva_la_proporcion_al_redimensionar(self, qtbot: QtBot) -> None:
        canvas = make_canvas(qtbot, page_width=400.0, page_height=300.0)
        canvas.set_objects([make_image(PdfRect(70, 10, 110, 30))])
        canvas.select_object("imagen-1")
        requests: list[tuple[str, PdfRect]] = []
        canvas.transform_requested.connect(lambda oid, rect: requests.append((oid, rect)))

        # Imagen de 40 x 20: el eje que más crece (vertical) marca la escala.
        qtbot.mousePress(canvas, Qt.MouseButton.LeftButton, pos=QPoint(110, 30))
        send_mouse_move(canvas, QPoint(170, 90), Qt.KeyboardModifier.ShiftModifier)
        qtbot.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=QPoint(170, 90))

        assert requests == [("imagen-1", PdfRect(70, 10, 230, 90))]
        resized = requests[0][1]
        assert resized.width / resized.height == pytest.approx(2.0)

    def test_sin_shift_la_imagen_se_estira(self, qtbot: QtBot) -> None:
        canvas = make_canvas(qtbot, page_width=400.0, page_height=300.0)
        canvas.set_objects([make_image(PdfRect(70, 10, 110, 30))])
        canvas.select_object("imagen-1")
        requests: list[tuple[str, PdfRect]] = []
        canvas.transform_requested.connect(lambda oid, rect: requests.append((oid, rect)))

        qtbot.mousePress(canvas, Qt.MouseButton.LeftButton, pos=QPoint(110, 30))
        qtbot.mouseMove(canvas, QPoint(170, 90))
        qtbot.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=QPoint(170, 90))

        assert requests == [("imagen-1", PdfRect(70, 10, 170, 90))]


class TestPintura:
    def test_marca_el_texto_que_no_cabe(self, qtbot: QtBot) -> None:
        canvas = make_canvas(qtbot)
        canvas.set_objects([make_text()])
        canvas.set_overflow_ids(["texto-1"])

        image = QImage(canvas.size(), QImage.Format.Format_RGB888)
        image.fill(QColor("#000000"))
        canvas.render(image)

        assert canvas.overflow_ids == frozenset({"texto-1"})
        border = [image.pixelColor(x, 20) for x in range(10, 61)]
        assert any(color.red() > 180 and color.green() < 140 for color in border)

    def test_pinta_el_texto_anadido(self, qtbot: QtBot) -> None:
        canvas = make_canvas(qtbot)
        canvas.set_objects([make_text()])

        pixmap = canvas.grab()

        colors = {
            pixmap.toImage().pixelColor(x, y).name() for x in range(15, 55) for y in range(25, 75)
        }
        assert "#000000" in colors

    def test_pinta_la_imagen_anadida(self, qtbot: QtBot) -> None:
        canvas = make_canvas(qtbot)
        canvas.set_objects([make_image()])

        pixmap = canvas.grab()

        assert pixmap.toImage().pixelColor(90, 30) == QColor("#ff0000")

    def test_pinta_la_region_seleccionada(self, qtbot: QtBot) -> None:
        canvas = make_canvas(qtbot)
        canvas.set_region(PdfRect(10, 20, 60, 80))

        pixmap = canvas.grab()

        assert pixmap.toImage().pixelColor(30, 50).name() != "#ffffff"
