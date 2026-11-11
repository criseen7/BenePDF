"""Pruebas de los modelos de edición y de la aplicación de comandos."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from bene.domain.editing import (
    AddImageCommand,
    AddRedactionCommand,
    AddStrokeCommand,
    AddTextCommand,
    DeleteObjectCommand,
    EditObject,
    ImageObject,
    MoveObjectCommand,
    RedactionObject,
    ResizeObjectCommand,
    StrokeObject,
    StrokeStyle,
    TextAlignment,
    TextObject,
    TextStyle,
    apply_command,
)
from bene.domain.errors import EditObjectNotFoundError, InvalidEditOperationError
from bene.domain.models import PdfRect


def text_object(object_id: str = "texto-1") -> TextObject:
    return TextObject(
        object_id=object_id,
        page_index=0,
        rect=PdfRect(10, 20, 210, 80),
        text="Hola",
    )


def stroke_object(object_id: str = "trazo-1") -> StrokeObject:
    return StrokeObject(
        object_id=object_id,
        page_index=0,
        points=((10.0, 20.0), (50.0, 40.0)),
        style=StrokeStyle(color="#ff0000", width=2.0),
    )


def image_object(object_id: str = "imagen-1") -> ImageObject:
    return ImageObject(
        object_id=object_id,
        page_index=0,
        rect=PdfRect(30, 40, 130, 140),
        data=b"\x89PNG\r\n\x1a\nfake",
        mime_type="image/png",
        source_path=Path("foto.png"),
    )


class TestTextStyle:
    def test_valores_por_defecto(self) -> None:
        style = TextStyle()

        assert style.font_name == "Helvetica"
        assert style.font_size == 12.0
        assert style.color == "#000000"
        assert style.alignment is TextAlignment.LEFT

    def test_rechaza_tamano_no_positivo(self) -> None:
        with pytest.raises(ValueError):
            TextStyle(font_size=0)

    def test_rechaza_color_no_hexadecimal(self) -> None:
        with pytest.raises(ValueError):
            TextStyle(color="rojo")

    def test_acepta_color_con_y_sin_mayusculas(self) -> None:
        assert TextStyle(color="#a1B2c3").color == "#a1B2c3"


class TestStrokeStyle:
    def test_valores_por_defecto(self) -> None:
        style = StrokeStyle()

        assert style.color == "#000000"
        assert style.width == 2.0

    @pytest.mark.parametrize("width", [0, -1, float("inf"), float("nan")])
    def test_rechaza_grosores_invalidos(self, width: float) -> None:
        with pytest.raises(ValueError):
            StrokeStyle(width=width)

    def test_rechaza_color_no_hexadecimal(self) -> None:
        with pytest.raises(ValueError):
            StrokeStyle(color="rojo")


class TestObjetos:
    def test_el_trazo_calcula_su_caja_incluido_el_grosor(self) -> None:
        stroke = stroke_object()

        assert stroke.rect == PdfRect(9, 19, 51, 41)

    def test_un_punto_aislado_tiene_area_seleccionable(self) -> None:
        stroke = StrokeObject(
            object_id="trazo-1",
            page_index=0,
            points=((10.0, 20.0),),
            style=StrokeStyle(width=6.0),
        )

        assert stroke.rect == PdfRect(7, 17, 13, 23)

    def test_el_trazo_valida_puntos_e_identidad(self) -> None:
        with pytest.raises(ValueError):
            StrokeObject(object_id="trazo-1", page_index=0, points=())
        with pytest.raises(ValueError):
            StrokeObject(
                object_id="trazo-1",
                page_index=0,
                points=((float("nan"), 20.0),),
            )
        with pytest.raises(ValueError):
            StrokeObject(object_id=" ", page_index=0, points=((10.0, 20.0),))
        with pytest.raises(ValueError):
            StrokeObject(object_id="trazo-1", page_index=-1, points=((10.0, 20.0),))

    def test_el_texto_valida_su_contenido_y_geometria(self) -> None:
        with pytest.raises(ValueError):
            TextObject(
                object_id="t",
                page_index=0,
                rect=PdfRect(0, 0, 10, 10),
                text="   ",
            )
        with pytest.raises(ValueError):
            TextObject(
                object_id="t",
                page_index=0,
                rect=PdfRect(0, 0, 0, 10),
                text="Hola",
            )

    def test_la_imagen_valida_tipo_y_datos(self) -> None:
        with pytest.raises(ValueError):
            ImageObject(
                object_id="i",
                page_index=0,
                rect=PdfRect(0, 0, 10, 10),
                data=b"x",
                mime_type="image/gif",
            )
        with pytest.raises(ValueError):
            ImageObject(
                object_id="i",
                page_index=0,
                rect=PdfRect(0, 0, 10, 10),
                data=b"",
                mime_type="image/png",
            )

    def test_la_redaccion_valida_su_geometria(self) -> None:
        with pytest.raises(ValueError):
            RedactionObject(object_id="r", page_index=0, rect=PdfRect(0, 0, 0, 10))
        with pytest.raises(ValueError):
            RedactionObject(object_id=" ", page_index=0, rect=PdfRect(0, 0, 10, 10))
        with pytest.raises(ValueError):
            RedactionObject(object_id="r", page_index=-1, rect=PdfRect(0, 0, 10, 10))

    def test_los_objetos_son_inmutables(self) -> None:
        obj = text_object()

        with pytest.raises(FrozenInstanceError):
            obj.text = "otro"  # type: ignore[misc]


class TestComandos:
    def test_anadir_texto_e_imagen(self) -> None:
        text = text_object()
        image = image_object()

        objects = apply_command({}, AddTextCommand(text))
        objects = apply_command(objects, AddImageCommand(image))

        assert objects == {"texto-1": text, "imagen-1": image}

    def test_anadir_trazo(self) -> None:
        stroke = stroke_object()

        objects = apply_command({}, AddStrokeCommand(stroke))

        assert objects == {"trazo-1": stroke}

    def test_mover_un_trazo_desplaza_sus_puntos(self) -> None:
        stroke = stroke_object()

        objects = apply_command(
            {"trazo-1": stroke},
            MoveObjectCommand("trazo-1", 0, PdfRect(19, 24, 61, 46)),
        )

        moved = objects["trazo-1"]
        assert isinstance(moved, StrokeObject)
        assert moved.points == ((20.0, 25.0), (60.0, 45.0))
        assert moved.rect == PdfRect(19, 24, 61, 46)

    def test_redimensionar_un_trazo_escala_sus_puntos(self) -> None:
        stroke = stroke_object()

        objects = apply_command(
            {"trazo-1": stroke},
            ResizeObjectCommand("trazo-1", 0, PdfRect(0, 0, 82, 42)),
        )

        resized = objects["trazo-1"]
        assert isinstance(resized, StrokeObject)
        assert resized.points == ((1.0, 1.0), (81.0, 41.0))
        assert resized.style.width == 2.0

    def test_anadir_redaccion(self) -> None:
        redaction = RedactionObject(
            object_id="redaccion-1",
            page_index=0,
            rect=PdfRect(10, 20, 110, 60),
        )

        objects = apply_command({}, AddRedactionCommand(redaction))

        assert objects == {"redaccion-1": redaction}

    def test_no_permite_identificadores_duplicados(self) -> None:
        text = text_object()

        with pytest.raises(InvalidEditOperationError):
            apply_command({"texto-1": text}, AddTextCommand(text))

    def test_mover_y_redimensionar(self) -> None:
        text = text_object()
        objects: dict[str, EditObject] = {"texto-1": text}

        objects = apply_command(objects, MoveObjectCommand("texto-1", 0, PdfRect(50, 60, 250, 120)))
        objects = apply_command(
            objects, ResizeObjectCommand("texto-1", 0, PdfRect(50, 60, 150, 90))
        )

        moved = objects["texto-1"]
        assert isinstance(moved, TextObject)
        assert moved.rect == PdfRect(50, 60, 150, 90)
        assert text.rect == PdfRect(10, 20, 210, 80)

    def test_no_permite_mover_un_objeto_inexistente(self) -> None:
        with pytest.raises(EditObjectNotFoundError):
            apply_command({}, MoveObjectCommand("fantasma", 0, PdfRect(0, 0, 10, 10)))

    def test_no_permite_mover_desde_otra_pagina(self) -> None:
        with pytest.raises(InvalidEditOperationError):
            apply_command(
                {"texto-1": text_object()},
                MoveObjectCommand("texto-1", 1, PdfRect(0, 0, 10, 10)),
            )

    def test_eliminar(self) -> None:
        objects = apply_command({"texto-1": text_object()}, DeleteObjectCommand("texto-1", 0))

        assert objects == {}

    def test_no_permite_eliminar_dos_veces(self) -> None:
        with pytest.raises(EditObjectNotFoundError):
            apply_command({}, DeleteObjectCommand("texto-1", 0))

    def test_el_rectangulo_de_un_comando_debe_ser_valido(self) -> None:
        with pytest.raises(ValueError):
            MoveObjectCommand("texto-1", 0, PdfRect(10, 10, 10, 10))
