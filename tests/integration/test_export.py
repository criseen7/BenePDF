"""Pruebas de integración de la exportación con PyMuPDF (RF-009, RNF-005, RNF-008)."""

from __future__ import annotations

from contextlib import closing
from pathlib import Path

import pymupdf
import pytest

from bene.application.use_cases.export_document import ExportDocument
from bene.domain.editing import (
    ImageObject,
    RedactionObject,
    StrokeObject,
    StrokeStyle,
    TextAlignment,
    TextObject,
    TextStyle,
)
from bene.domain.errors import ExportError
from bene.domain.models import PdfRect
from bene.domain.pages import PageArrangement
from bene.infrastructure.pdf.pymupdf_engine import PyMuPDFEngine
from tests.integration import synthetic


@pytest.fixture
def engine() -> PyMuPDFEngine:
    return PyMuPDFEngine()


def export(
    engine: PyMuPDFEngine,
    source: Path,
    destination: Path,
    objects: tuple[TextObject | ImageObject | RedactionObject | StrokeObject, ...],
    arrangement: PageArrangement | None = None,
) -> None:
    with closing(engine.open_document(source)) as document:
        ExportDocument()(document, destination, objects=objects, arrangement=arrangement)


def text_of(path: Path) -> str:
    with pymupdf.open(path) as document:
        return "\n".join(page.get_text("text") for page in document)


def png_bytes() -> bytes:
    document = pymupdf.open()
    page = document.new_page(width=40, height=20)
    page.draw_rect(page.rect, color=(0, 0, 0), fill=(0, 0, 0))
    pixmap = page.get_pixmap(alpha=False)
    document.close()
    return pixmap.tobytes("png")


def colored_png_bytes(width: int = 100, height: int = 50) -> bytes:
    """PNG con un color distinto en cada esquina para detectar la orientación."""
    document = pymupdf.open()
    page = document.new_page(width=width, height=height)
    page.draw_rect(pymupdf.Rect(0, 0, width / 2, height / 2), color=(1, 0, 0), fill=(1, 0, 0))
    page.draw_rect(pymupdf.Rect(width / 2, 0, width, height / 2), color=(0, 0, 1), fill=(0, 0, 1))
    page.draw_rect(pymupdf.Rect(0, height / 2, width / 2, height), color=(0, 1, 0), fill=(0, 1, 0))
    pixmap = page.get_pixmap(alpha=False)
    document.close()
    return pixmap.tobytes("png")


def displayed_lines(page: pymupdf.Page) -> list[tuple[str, pymupdf.Rect]]:
    """Líneas de texto con su caja en coordenadas visibles (tras ``/Rotate``)."""
    lines: list[tuple[str, pymupdf.Rect]] = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            text = "".join(span["text"] for span in line["spans"])
            lines.append((text, pymupdf.Rect(line["bbox"]) * page.rotation_matrix))
    return lines


def dark_bbox(image: pymupdf.Pixmap, rect: pymupdf.Rect) -> tuple[int, int, int, int] | None:
    """Caja de píxeles oscuros dentro de ``rect`` (coordenadas de la imagen)."""
    x0 = max(0, round(rect.x0))
    y0 = max(0, round(rect.y0))
    x1 = min(image.width, round(rect.x1))
    y1 = min(image.height, round(rect.y1))
    min_x, min_y, max_x, max_y = x1, y1, x0 - 1, y0 - 1
    for y in range(y0, y1):
        for x in range(x0, x1):
            pixel = image.pixel(x, y)
            if pixel[0] < 100 and pixel[1] < 100 and pixel[2] < 100:
                min_x, min_y = min(min_x, x), min(min_y, y)
                max_x, max_y = max(max_x, x), max(max_y, y)
    if max_x < x0:
        return None
    return (min_x, min_y, max_x + 1, max_y + 1)


def non_white_bbox(image: pymupdf.Pixmap, rect: pymupdf.Rect) -> tuple[int, int, int, int] | None:
    """Caja de píxeles no blancos dentro de ``rect`` (coordenadas de la imagen)."""
    x0 = max(0, round(rect.x0))
    y0 = max(0, round(rect.y0))
    x1 = min(image.width, round(rect.x1))
    y1 = min(image.height, round(rect.y1))
    min_x, min_y, max_x, max_y = x1, y1, x0 - 1, y0 - 1
    for y in range(y0, y1):
        for x in range(x0, x1):
            pixel = image.pixel(x, y)
            if not (pixel[0] > 245 and pixel[1] > 245 and pixel[2] > 245):
                min_x, min_y = min(min_x, x), min(min_y, y)
                max_x, max_y = max(max_x, x), max(max_y, y)
    if max_x < x0:
        return None
    return (min_x, min_y, max_x + 1, max_y + 1)


class TestExportacion:
    def test_anade_texto_sin_modificar_el_original(
        self, engine: PyMuPDFEngine, tmp_path: Path
    ) -> None:
        source = synthetic.make_text_pdf(tmp_path / "original.pdf")
        original = source.read_bytes()
        destination = tmp_path / "copia.pdf"
        obj = TextObject(
            object_id="texto-1",
            page_index=0,
            rect=PdfRect(60, 200, 400, 240),
            text="TEXTO AÑADIDO",
            style=TextStyle(font_size=14, color="#ff0000"),
        )

        export(engine, source, destination, (obj,))

        assert source.read_bytes() == original
        assert destination.exists()
        exported = text_of(destination)
        assert "TEXTO AÑADIDO" in exported
        assert "Contrato de prueba" in exported

    def test_la_redaccion_elimina_el_texto_subyacente(
        self, engine: PyMuPDFEngine, tmp_path: Path
    ) -> None:
        source = synthetic.make_text_pdf(tmp_path / "original.pdf")
        destination = tmp_path / "redactado.pdf"
        redaction = RedactionObject(
            object_id="redaccion-1",
            page_index=0,
            rect=PdfRect(60, 80, 500, 120),
        )

        export(engine, source, destination, (redaction,))

        assert "Contrato de prueba" in text_of(source)
        exported = text_of(destination)
        assert "Contrato de prueba" not in exported
        assert "Texto nativo seleccionable" in exported

    def test_la_redaccion_elimina_anotaciones_y_campos_que_intersectan(
        self, engine: PyMuPDFEngine, tmp_path: Path
    ) -> None:
        source = synthetic.make_annotation_form_pdf(tmp_path / "anotado.pdf")
        destination = tmp_path / "anotado-redactado.pdf"
        redaction = RedactionObject("redaccion-1", 0, PdfRect(50, 50, 380, 260))

        export(engine, source, destination, (redaction,))

        exported = text_of(destination)
        assert "Texto sensible" not in exported
        assert "Valor sensible" not in exported
        assert "Texto visible" in exported
        with pymupdf.open(destination) as document:
            page = document[0]
            annotations = list(page.annots()) if page.annots() is not None else []
            widgets = list(page.widgets()) if page.widgets() is not None else []
            assert len(annotations) == 1
            assert annotations[0].rect.y0 > 500
            assert [widget.field_name for widget in widgets] == ["campo_fuera"]

    def test_la_redaccion_elimina_el_texto_parcialmente_intersectado(
        self, engine: PyMuPDFEngine, tmp_path: Path
    ) -> None:
        source = synthetic.make_text_pdf(tmp_path / "original.pdf")
        destination = tmp_path / "parcial.pdf"
        redaction = RedactionObject("redaccion-1", 0, PdfRect(60, 80, 120, 120))

        export(engine, source, destination, (redaction,))

        exported = text_of(destination)
        assert "Contrato" not in exported
        assert "prueba" in exported

    def test_la_redaccion_elimina_los_vectores_que_intersectan(
        self, engine: PyMuPDFEngine, tmp_path: Path
    ) -> None:
        source = synthetic.make_graphic_pdf(tmp_path / "grafico.pdf")
        destination = tmp_path / "grafico-redactado.pdf"
        redaction = RedactionObject("redaccion-1", 0, PdfRect(80, 80, 420, 320))

        export(engine, source, destination, (redaction,))

        with pymupdf.open(destination) as document:
            page = document[0]
            pixmap = page.get_pixmap(alpha=False)
            assert pixmap.pixel(200, 200) == (0, 0, 0)
            # La línea queda fuera de la redacción y se conserva (con su
            # suavizado de bordes); el relleno de la redacción es negro.
            line = pixmap.pixel(200, 400)
            assert max(line) < 200

    def test_redactar_y_escribir_texto_nuevo(self, engine: PyMuPDFEngine, tmp_path: Path) -> None:
        source = synthetic.make_text_pdf(tmp_path / "original.pdf")
        destination = tmp_path / "reemplazado.pdf"
        objects = (
            RedactionObject("redaccion-1", 0, PdfRect(60, 80, 500, 120)),
            TextObject(
                "texto-1",
                0,
                PdfRect(60, 80, 500, 120),
                "REEMPLAZO",
                TextStyle(font_size=14),
            ),
        )

        export(engine, source, destination, objects)

        exported = text_of(destination)
        assert "Contrato de prueba" not in exported
        assert "REEMPLAZO" in exported

    def test_la_redaccion_en_un_escaneo_conserva_el_resto_de_la_pagina(
        self, engine: PyMuPDFEngine, tmp_path: Path
    ) -> None:
        source = synthetic.make_scanned_pdf(tmp_path / "escaneo.pdf")
        destination = tmp_path / "escaneo-redactado.pdf"
        redaction = RedactionObject("redaccion-1", 0, PdfRect(60, 80, 300, 120))

        export(engine, source, destination, (redaction,))

        with pymupdf.open(destination) as document:
            page = document[0]
            # La imagen se conserva; solo se eliminan los píxeles de la región.
            assert len(page.get_images()) == 1
            pixmap = page.get_pixmap(alpha=False)
            assert pixmap.pixel(100, 100) == (0, 0, 0)
            assert pixmap.pixel(400, 400)[0] > 200

    def test_inserta_una_imagen(self, engine: PyMuPDFEngine, tmp_path: Path) -> None:
        source = synthetic.make_empty_pdf(tmp_path / "original.pdf")
        destination = tmp_path / "con-imagen.pdf"
        obj = ImageObject(
            "imagen-1",
            0,
            PdfRect(50, 50, 250, 150),
            png_bytes(),
            "image/png",
        )

        export(engine, source, destination, (obj,))

        with pymupdf.open(destination) as document:
            page = document[0]
            assert len(page.get_images()) == 1
            pixmap = page.get_pixmap(alpha=False)
            assert dark_bbox(pixmap, pymupdf.Rect(60, 60, 240, 140)) is not None

    def test_conserva_el_euro_y_los_acentos(self, engine: PyMuPDFEngine, tmp_path: Path) -> None:
        source = synthetic.make_empty_pdf(tmp_path / "original.pdf")
        destination = tmp_path / "unicode.pdf"
        obj = TextObject(
            "texto-1",
            0,
            PdfRect(50, 50, 450, 90),
            "Precio: 10 € - Añoranza, pingüino, cañón",
            TextStyle(font_size=14),
        )

        export(engine, source, destination, (obj,))

        with pymupdf.open(destination) as document:
            words = [word[4].replace("\xa0", " ") for word in document[0].get_text("words")]
        assert "€" in words
        assert "Añoranza," in words
        assert "pingüino," in words
        assert "cañón" in words

    def test_el_aviso_de_texto_que_no_cabe_identifica_el_objeto(
        self, engine: PyMuPDFEngine, tmp_path: Path
    ) -> None:
        source = synthetic.make_empty_pdf(tmp_path / "original.pdf")
        destination = tmp_path / "salida.pdf"
        obj = TextObject(
            "texto-largo-1",
            0,
            PdfRect(50, 50, 120, 70),
            "X" * 500,
            TextStyle(font_size=14),
        )

        with (
            closing(engine.open_document(source)) as document,
            pytest.raises(ExportError) as info,
        ):
            ExportDocument()(document, destination, objects=(obj,))

        message = str(info.value)
        assert "texto-largo-1" in message
        assert "página 1" in message
        assert "faltan" in message.lower()
        assert not destination.exists()

    def test_un_fallo_no_modifica_un_destino_existente(
        self, engine: PyMuPDFEngine, tmp_path: Path
    ) -> None:
        source = synthetic.make_empty_pdf(tmp_path / "original.pdf")
        destination = tmp_path / "existente.pdf"
        destination.write_bytes(b"CONTENIDO ANTERIOR")
        obj = TextObject(
            "texto-1",
            0,
            PdfRect(50, 50, 120, 70),
            "X" * 500,
            TextStyle(font_size=14),
        )

        with (
            closing(engine.open_document(source)) as document,
            pytest.raises(ExportError) as info,
        ):
            ExportDocument()(document, destination, objects=(obj,))

        assert destination.read_bytes() == b"CONTENIDO ANTERIOR"
        assert "no se ha modificado" in str(info.value)

    def test_rechaza_el_mismo_archivo(self, engine: PyMuPDFEngine, tmp_path: Path) -> None:
        source = synthetic.make_text_pdf(tmp_path / "original.pdf")
        original = source.read_bytes()

        with (
            closing(engine.open_document(source)) as document,
            pytest.raises(ExportError, match="distinto del PDF original"),
        ):
            ExportDocument()(document, source, objects=())

        assert source.read_bytes() == original

    def test_no_deja_archivos_temporales(self, engine: PyMuPDFEngine, tmp_path: Path) -> None:
        source = synthetic.make_text_pdf(tmp_path / "original.pdf")
        destination = tmp_path / "copia.pdf"

        export(engine, source, destination, ())

        assert sorted(path.name for path in tmp_path.iterdir()) == [
            "copia.pdf",
            "original.pdf",
        ]

    def test_rechaza_la_exportacion_de_un_pdf_cifrado(
        self, engine: PyMuPDFEngine, tmp_path: Path
    ) -> None:
        source = synthetic.make_encrypted_pdf(tmp_path / "cifrado.pdf")
        original = source.read_bytes()
        destination = tmp_path / "cifrado-copia.pdf"

        with (
            closing(engine.open_document(source, password="clave")) as document,
            pytest.raises(ExportError, match="cifrado"),
        ):
            ExportDocument()(document, destination, objects=())

        assert source.read_bytes() == original
        assert not destination.exists()

    def test_rechaza_objetos_en_paginas_inexistentes(
        self, engine: PyMuPDFEngine, tmp_path: Path
    ) -> None:
        source = synthetic.make_text_pdf(tmp_path / "original.pdf")
        obj = TextObject("texto-1", 5, PdfRect(10, 10, 100, 40), "Fuera")

        with (
            closing(engine.open_document(source)) as document,
            pytest.raises(ExportError, match="página que no existe"),
        ):
            document.export_to(tmp_path / "copia.pdf", objects=(obj,))

        assert not (tmp_path / "copia.pdf").exists()


class TestFallosDelSistemaDeArchivos:
    @pytest.mark.parametrize(
        "error",
        [
            PermissionError(13, "Permiso denegado"),
            OSError(28, "No queda espacio en el dispositivo"),
        ],
    )
    def test_un_fallo_al_crear_el_temporal_es_accionable(
        self,
        engine: PyMuPDFEngine,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        error: OSError,
    ) -> None:
        source = synthetic.make_text_pdf(tmp_path / "original.pdf")
        destination = tmp_path / "copia.pdf"

        def fallar(*_args: object, **_kwargs: object) -> tuple[int, str]:
            raise error

        monkeypatch.setattr("bene.infrastructure.pdf.pymupdf_engine.tempfile.mkstemp", fallar)

        with (
            closing(engine.open_document(source)) as document,
            pytest.raises(ExportError) as info,
        ):
            document.export_to(destination, objects=())

        message = str(info.value)
        assert "No se pudo crear el archivo temporal" in message
        assert str(tmp_path) in message
        assert str(error) in message
        assert "permisos" in message.lower()
        assert "espacio" in message.lower()
        assert not destination.exists()

    @pytest.mark.parametrize(
        "error",
        [
            PermissionError(13, "Permiso denegado"),
            OSError(28, "No queda espacio en el dispositivo"),
        ],
    )
    def test_un_fallo_al_reemplazar_el_destino_no_lo_dana(
        self,
        engine: PyMuPDFEngine,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        error: OSError,
    ) -> None:
        source = synthetic.make_text_pdf(tmp_path / "original.pdf")
        destination = tmp_path / "existente.pdf"
        destination.write_bytes(b"CONTENIDO ANTERIOR")

        def fallar(_self: Path, _target: Path) -> Path:
            raise error

        monkeypatch.setattr(Path, "replace", fallar)

        with (
            closing(engine.open_document(source)) as document,
            pytest.raises(ExportError) as info,
        ):
            document.export_to(destination, objects=())

        message = str(info.value)
        assert str(error) in message
        assert "permisos" in message.lower()
        assert "espacio" in message.lower()
        assert "no se ha modificado" in message.lower()
        assert destination.read_bytes() == b"CONTENIDO ANTERIOR"
        assert sorted(path.name for path in tmp_path.iterdir()) == [
            "existente.pdf",
            "original.pdf",
        ]

    def test_exporta_a_una_ruta_unicode_con_espacios(
        self, engine: PyMuPDFEngine, tmp_path: Path
    ) -> None:
        source = synthetic.make_text_pdf(tmp_path / "original.pdf")
        folder = tmp_path / "carpeta con espacios"
        folder.mkdir()
        destination = folder / "copia final (versión 2).pdf"

        export(engine, source, destination, ())

        assert destination.is_file()
        with pymupdf.open(destination) as document:
            assert document.page_count == 1


class TestPaginasRotadas:
    @pytest.mark.parametrize("rotation", [0, 90, 180, 270])
    def test_el_texto_nuevo_queda_horizontal_y_en_su_region(
        self, engine: PyMuPDFEngine, tmp_path: Path, rotation: int
    ) -> None:
        source = synthetic.make_rotated_empty_pdf(
            tmp_path / f"rotado-{rotation}.pdf", rotation=rotation
        )
        destination = tmp_path / f"salida-{rotation}.pdf"
        visible = PdfRect(50, 50, 250, 100)
        obj = TextObject("texto-1", 0, visible, "ROTADO", TextStyle(font_size=14))

        export(engine, source, destination, (obj,))

        with pymupdf.open(destination) as document:
            page = document[0]
            assert page.rotation == rotation
            assert "ROTADO" in page.get_text("text")
            pixmap = page.get_pixmap(alpha=False)
            bbox = dark_bbox(pixmap, pymupdf.Rect(visible.x0, visible.y0, visible.x1, visible.y1))
            assert bbox is not None
            width = bbox[2] - bbox[0]
            height = bbox[3] - bbox[1]
            assert width > height * 2

    @pytest.mark.parametrize("rotation", [0, 90, 180, 270])
    @pytest.mark.parametrize("alignment", list(TextAlignment))
    def test_el_texto_multilinea_respeta_orden_alineacion_y_region(
        self,
        engine: PyMuPDFEngine,
        tmp_path: Path,
        rotation: int,
        alignment: TextAlignment,
    ) -> None:
        source = synthetic.make_rotated_empty_pdf(
            tmp_path / f"rotado-multilinea-{rotation}.pdf", rotation=rotation
        )
        destination = tmp_path / f"salida-multilinea-{rotation}-{alignment.value}.pdf"
        visible = PdfRect(50, 50, 350, 160)
        obj = TextObject(
            "texto-1",
            0,
            visible,
            "LINEA UNO\nLINEA DOS\nLINEA TRES",
            TextStyle(font_size=14, alignment=alignment),
        )

        export(engine, source, destination, (obj,))

        with pymupdf.open(destination) as document:
            page = document[0]
            assert page.rotation == rotation
            lines = displayed_lines(page)
            assert [text for text, _ in lines] == ["LINEA UNO", "LINEA DOS", "LINEA TRES"]

            # El orden visual es de arriba hacia abajo, no el inverso.
            tops = [bbox.y0 for _, bbox in lines]
            assert tops == sorted(tops)

            for _, bbox in lines:
                assert visible.x0 - 2 <= bbox.x0
                assert bbox.x1 <= visible.x1 + 2
                assert visible.y0 - 2 <= bbox.y0
                assert bbox.y1 <= visible.y1 + 2

            if alignment is TextAlignment.LEFT:
                for _, bbox in lines:
                    assert bbox.x0 == pytest.approx(visible.x0, abs=2)
            elif alignment is TextAlignment.CENTER:
                center = (visible.x0 + visible.x1) / 2
                for _, bbox in lines:
                    assert (bbox.x0 + bbox.x1) / 2 == pytest.approx(center, abs=2)
            else:
                for _, bbox in lines:
                    assert bbox.x1 == pytest.approx(visible.x1, abs=2)

    @pytest.mark.parametrize("rotation", [0, 90, 180, 270])
    def test_la_imagen_nueva_queda_en_su_region(
        self, engine: PyMuPDFEngine, tmp_path: Path, rotation: int
    ) -> None:
        source = synthetic.make_rotated_empty_pdf(
            tmp_path / f"rotado-imagen-{rotation}.pdf", rotation=rotation
        )
        destination = tmp_path / f"salida-imagen-{rotation}.pdf"
        visible = PdfRect(50, 50, 250, 150)
        obj = ImageObject("imagen-1", 0, visible, png_bytes(), "image/png")

        export(engine, source, destination, (obj,))

        with pymupdf.open(destination) as document:
            page = document[0]
            assert page.rotation == rotation
            pixmap = page.get_pixmap(alpha=False)
            bbox = dark_bbox(pixmap, pymupdf.Rect(0, 0, pixmap.width, pixmap.height))
            assert bbox is not None
            assert bbox == pytest.approx((visible.x0, visible.y0, visible.x1, visible.y1), abs=1)

    @pytest.mark.parametrize("rotation", [0, 90, 180, 270])
    def test_la_imagen_queda_bien_con_cropbox_desplazado(
        self, engine: PyMuPDFEngine, tmp_path: Path, rotation: int
    ) -> None:
        source = synthetic.make_cropped_rotated_pdf(
            tmp_path / f"recortado-{rotation}.pdf", rotation=rotation
        )
        destination = tmp_path / f"salida-recortada-{rotation}.pdf"
        visible = PdfRect(50, 50, 250, 150)
        obj = ImageObject("imagen-1", 0, visible, colored_png_bytes(), "image/png")

        export(engine, source, destination, (obj,))

        with pymupdf.open(destination) as document:
            page = document[0]
            assert page.rotation == rotation
            pixmap = page.get_pixmap(alpha=False)
            bbox = non_white_bbox(pixmap, pymupdf.Rect(0, 0, pixmap.width, pixmap.height))
            assert bbox is not None
            assert bbox == pytest.approx((visible.x0, visible.y0, visible.x1, visible.y1), abs=1)

            # La orientación de la imagen no se invierte al rotar la página.
            x0, y0, x1, y1 = bbox
            top_left = pixmap.pixel(x0 + 5, y0 + 5)
            top_right = pixmap.pixel(x1 - 5, y0 + 5)
            bottom_left = pixmap.pixel(x0 + 5, y1 - 5)
            bottom_right = pixmap.pixel(x1 - 5, y1 - 5)
            assert top_left[0] > 200 and max(top_left[1:]) < 80
            assert top_right[2] > 200 and max(top_right[0], top_right[1]) < 80
            assert bottom_left[1] > 200 and max(bottom_left[0], bottom_left[2]) < 80
            assert min(bottom_right) > 240

    @pytest.mark.parametrize("rotation", [90, 270])
    def test_la_redaccion_usa_las_coordenadas_visibles(
        self, engine: PyMuPDFEngine, tmp_path: Path, rotation: int
    ) -> None:
        source = synthetic.make_rotated_pdf(
            tmp_path / f"original-{rotation}.pdf", rotation=rotation
        )
        destination = tmp_path / f"redactado-{rotation}.pdf"
        # El texto original está en (72, 100) sin rotar. Se calcula su
        # posición visible con la matriz de rotación de la página.
        with pymupdf.open(source) as document:
            page = document[0]
            visible = pymupdf.Rect(60, 80, 300, 120) * page.rotation_matrix
        redaction = RedactionObject(
            "redaccion-1",
            0,
            PdfRect(visible.x0, visible.y0, visible.x1, visible.y1),
        )

        export(engine, source, destination, (redaction,))

        assert "Página rotada" not in text_of(destination)


class TestTrazos:
    def test_exporta_color_grosor_y_posicion(self, engine: PyMuPDFEngine, tmp_path: Path) -> None:
        source = synthetic.make_empty_pdf(tmp_path / "original.pdf")
        original = source.read_bytes()
        destination = tmp_path / "con-trazo.pdf"
        style = StrokeStyle(color="#ff0000", width=6.0)
        obj = StrokeObject(
            "trazo-1",
            0,
            ((100.0, 100.0), (200.0, 100.0), (200.0, 150.0)),
            style,
        )

        export(engine, source, destination, (obj,))

        assert source.read_bytes() == original
        with pymupdf.open(destination) as document:
            page = document[0]
            drawings = [item for item in page.get_drawings() if item["color"] is not None]
            assert drawings
            drawing = drawings[-1]
            assert drawing["color"] == pytest.approx((1.0, 0.0, 0.0))
            assert drawing["width"] == pytest.approx(style.width)
            pixmap = page.get_pixmap(alpha=False)
            bbox = non_white_bbox(pixmap, pymupdf.Rect(90, 90, 210, 160))
            assert bbox == pytest.approx((97, 97, 203, 153), abs=3)

    @pytest.mark.parametrize("rotation", [0, 90, 180, 270])
    def test_el_trazo_respeta_la_rotacion_de_la_pagina(
        self, engine: PyMuPDFEngine, tmp_path: Path, rotation: int
    ) -> None:
        source = synthetic.make_rotated_empty_pdf(
            tmp_path / f"trazo-rotado-{rotation}.pdf", rotation=rotation
        )
        destination = tmp_path / f"trazo-salida-{rotation}.pdf"
        obj = StrokeObject(
            "trazo-1",
            0,
            ((50.0, 50.0), (150.0, 50.0)),
            StrokeStyle(color="#0000ff", width=4.0),
        )

        export(engine, source, destination, (obj,))

        with pymupdf.open(destination) as document:
            page = document[0]
            assert page.rotation == rotation
            pixmap = page.get_pixmap(alpha=False)
            bbox = non_white_bbox(pixmap, pymupdf.Rect(0, 0, pixmap.width, pixmap.height))
            assert bbox == pytest.approx((48, 48, 152, 52), abs=3)

    @pytest.mark.parametrize("rotation", [0, 90, 180, 270])
    def test_el_trazo_respeta_el_cropbox_desplazado(
        self, engine: PyMuPDFEngine, tmp_path: Path, rotation: int
    ) -> None:
        source = synthetic.make_cropped_rotated_pdf(
            tmp_path / f"trazo-recortado-{rotation}.pdf", rotation=rotation
        )
        destination = tmp_path / f"trazo-recortado-salida-{rotation}.pdf"
        obj = StrokeObject(
            "trazo-1",
            0,
            ((50.0, 50.0), (150.0, 50.0)),
            StrokeStyle(color="#008000", width=4.0),
        )

        export(engine, source, destination, (obj,))

        with pymupdf.open(destination) as document:
            page = document[0]
            pixmap = page.get_pixmap(alpha=False)
            bbox = non_white_bbox(pixmap, pymupdf.Rect(0, 0, pixmap.width, pixmap.height))
            assert bbox == pytest.approx((48, 48, 152, 52), abs=3)

    def test_la_rotacion_adicional_arrastra_el_trazo(
        self, engine: PyMuPDFEngine, tmp_path: Path
    ) -> None:
        source = synthetic.make_empty_pdf(tmp_path / "original.pdf")
        destination = tmp_path / "trazo-rotacion-extra.pdf"
        obj = StrokeObject(
            "trazo-1",
            0,
            ((100.0, 100.0), (200.0, 100.0)),
            StrokeStyle(color="#ff00ff", width=5.0),
        )

        export(
            engine,
            source,
            destination,
            (obj,),
            arrangement=PageArrangement(1, order=(0,), rotations={0: 90}),
        )

        with pymupdf.open(destination) as document:
            page = document[0]
            assert page.rotation == 90
            drawings = [item for item in page.get_drawings() if item["color"] is not None]
            assert drawings
            assert drawings[-1]["color"] == pytest.approx((1.0, 0.0, 1.0))

    def test_un_punto_aislado_se_exporta_como_punto(
        self, engine: PyMuPDFEngine, tmp_path: Path
    ) -> None:
        source = synthetic.make_empty_pdf(tmp_path / "original.pdf")
        destination = tmp_path / "punto.pdf"
        obj = StrokeObject(
            "trazo-1",
            0,
            ((100.0, 100.0),),
            StrokeStyle(color="#000000", width=10.0),
        )

        export(engine, source, destination, (obj,))

        with pymupdf.open(destination) as document:
            page = document[0]
            pixmap = page.get_pixmap(alpha=False)
            bbox = non_white_bbox(pixmap, pymupdf.Rect(90, 90, 110, 110))
            assert bbox == pytest.approx((95, 95, 105, 105), abs=2)

    def test_el_trazo_se_dibuja_sobre_una_redaccion(
        self, engine: PyMuPDFEngine, tmp_path: Path
    ) -> None:
        source = synthetic.make_text_pdf(tmp_path / "original.pdf")
        destination = tmp_path / "redactado-con-trazo.pdf"
        objects = (
            RedactionObject("redaccion-1", 0, PdfRect(60, 80, 500, 120)),
            StrokeObject(
                "trazo-1",
                0,
                ((100.0, 150.0), (300.0, 150.0)),
                StrokeStyle(color="#ff0000", width=6.0),
            ),
        )

        export(engine, source, destination, objects)

        assert "Contrato de prueba" not in text_of(destination)
        with pymupdf.open(destination) as document:
            page = document[0]
            pixmap = page.get_pixmap(alpha=False)
            pixel = pixmap.pixel(200, 150)
            assert pixel[0] > 200 and max(pixel[1:]) < 80

    def test_el_trazo_de_una_pagina_eliminada_no_se_exporta(
        self, engine: PyMuPDFEngine, tmp_path: Path
    ) -> None:
        source = synthetic.make_text_pdf(tmp_path / "original.pdf", pages=2)
        destination = tmp_path / "sin-segunda.pdf"
        obj = StrokeObject("trazo-1", 1, ((100.0, 100.0), (200.0, 100.0)))

        export(
            engine,
            source,
            destination,
            (obj,),
            arrangement=PageArrangement(2, order=(0,)),
        )

        with pymupdf.open(destination) as document:
            assert document.page_count == 1
            assert not document[0].get_drawings()
