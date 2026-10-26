"""Pruebas de integración de la exportación con PyMuPDF (RF-009, RNF-005, RNF-008)."""

from __future__ import annotations

from contextlib import closing
from pathlib import Path

import pymupdf
import pytest

from bene.application.use_cases.export_document import ExportDocument
from bene.domain.editing import ImageObject, RedactionObject, TextObject, TextStyle
from bene.domain.errors import ExportError
from bene.domain.models import PdfRect
from bene.infrastructure.pdf.pymupdf_engine import PyMuPDFEngine
from tests.integration import synthetic


@pytest.fixture
def engine() -> PyMuPDFEngine:
    return PyMuPDFEngine()


def export(
    engine: PyMuPDFEngine,
    source: Path,
    destination: Path,
    objects: tuple[TextObject | ImageObject | RedactionObject, ...],
) -> None:
    with closing(engine.open_document(source)) as document:
        ExportDocument()(document, destination, objects=objects)


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
