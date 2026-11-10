"""Pruebas de integración de las funciones de documento (RF-013, RF-020 a RF-023)."""

from __future__ import annotations

from contextlib import closing
from pathlib import Path

import pymupdf
import pytest

from bene.application.use_cases.export_document import ExportDocument
from bene.domain.editing import ImageReplacementObject, TextObject
from bene.domain.errors import DocumentClosedError
from bene.domain.models import PdfRect
from bene.domain.pages import PageArrangement, parse_page_selection
from bene.infrastructure.pdf.pymupdf_engine import PyMuPDFEngine
from tests.integration import synthetic


@pytest.fixture
def engine() -> PyMuPDFEngine:
    return PyMuPDFEngine()


def png_bytes(color: tuple[float, float, float], width: int = 40, height: int = 20) -> bytes:
    document = pymupdf.open()
    page = document.new_page(width=width, height=height)
    page.draw_rect(page.rect, color=color, fill=color)
    pixmap = page.get_pixmap(alpha=False)
    document.close()
    return pixmap.tobytes("png")


def page_texts(path: Path) -> list[str]:
    with pymupdf.open(path) as document:
        return [page.get_text("text") for page in document]


def export(
    engine: PyMuPDFEngine,
    source: Path,
    destination: Path,
    arrangement: PageArrangement,
    objects: tuple[ImageReplacementObject, ...] = (),
) -> None:
    with closing(engine.open_document(source)) as document:
        ExportDocument()(document, destination, objects=objects, arrangement=arrangement)


class TestTamanoDePagina:
    def test_tamano_visible_sin_rotacion(self, engine: PyMuPDFEngine, tmp_path: Path) -> None:
        source = synthetic.make_text_pdf(tmp_path / "documento.pdf")

        with closing(engine.open_document(source)) as document:
            width, height = document.page_size(0)

        assert (width, height) == pytest.approx((synthetic.A4_WIDTH, synthetic.A4_HEIGHT))

    def test_tamano_visible_con_rotacion(self, engine: PyMuPDFEngine, tmp_path: Path) -> None:
        source = synthetic.make_rotated_pdf(tmp_path / "rotado.pdf")

        with closing(engine.open_document(source)) as document:
            width, height = document.page_size(0)

        assert (width, height) == pytest.approx((synthetic.A4_HEIGHT, synthetic.A4_WIDTH))

    def test_tamano_visible_con_cropbox_y_rotacion(
        self, engine: PyMuPDFEngine, tmp_path: Path
    ) -> None:
        source = synthetic.make_cropped_rotated_pdf(tmp_path / "recortado.pdf")

        with closing(engine.open_document(source)) as document:
            width, height = document.page_size(0)

        assert (width, height) == pytest.approx((682.0, 495.0))


class TestBusqueda:
    def test_encuentra_en_todas_las_paginas(self, engine: PyMuPDFEngine, tmp_path: Path) -> None:
        source = synthetic.make_text_pdf(tmp_path / "documento.pdf", pages=3)

        with closing(engine.open_document(source)) as document:
            matches = document.search_text("Contrato de prueba")

        assert [match.page_index for match in matches] == [0, 1, 2]
        assert all(match.rect.width > 0 and match.rect.height > 0 for match in matches)
        assert all("Contrato de prueba" in match.snippet for match in matches)

    def test_encuentra_una_pagina_concreta(self, engine: PyMuPDFEngine, tmp_path: Path) -> None:
        source = synthetic.make_text_pdf(tmp_path / "documento.pdf", pages=3)

        with closing(engine.open_document(source)) as document:
            matches = document.search_text("página 2")

        assert len(matches) == 1
        assert matches[0].page_index == 1

    def test_la_busqueda_vacia_no_recorre_el_documento(
        self, engine: PyMuPDFEngine, tmp_path: Path
    ) -> None:
        source = synthetic.make_text_pdf(tmp_path / "documento.pdf")

        with closing(engine.open_document(source)) as document:
            assert document.search_text("   ") == ()

    def test_sin_resultados(self, engine: PyMuPDFEngine, tmp_path: Path) -> None:
        source = synthetic.make_text_pdf(tmp_path / "documento.pdf")

        with closing(engine.open_document(source)) as document:
            assert document.search_text("inexistente") == ()

    def test_las_coordenadas_estan_en_el_espacio_visible(
        self, engine: PyMuPDFEngine, tmp_path: Path
    ) -> None:
        source = synthetic.make_rotated_pdf(tmp_path / "rotado.pdf")

        with closing(engine.open_document(source)) as document:
            matches = document.search_text("Página rotada")

        assert len(matches) == 1
        rect = matches[0].rect
        assert 0 <= rect.x0 < rect.x1 <= synthetic.A4_HEIGHT
        assert 0 <= rect.y0 < rect.y1 <= synthetic.A4_WIDTH

    def test_las_coordenadas_respetan_el_cropbox(
        self, engine: PyMuPDFEngine, tmp_path: Path
    ) -> None:
        source = synthetic.make_cropped_rotated_text_pdf(tmp_path / "recortado.pdf")

        with closing(engine.open_document(source)) as document:
            matches = document.search_text("Texto recortado")

        assert len(matches) == 1
        rect = matches[0].rect
        assert 0 <= rect.x0 < rect.x1 <= 682.0
        assert 0 <= rect.y0 < rect.y1 <= 495.0

    def test_tras_cerrar_el_documento(self, engine: PyMuPDFEngine, tmp_path: Path) -> None:
        source = synthetic.make_text_pdf(tmp_path / "documento.pdf")
        document = engine.open_document(source)
        document.close()

        with pytest.raises(DocumentClosedError):
            document.search_text("Contrato")


class TestImagenesIncrustadas:
    def test_detecta_la_imagen_y_su_region(self, engine: PyMuPDFEngine, tmp_path: Path) -> None:
        source = synthetic.make_image_pdf(tmp_path / "imagen.pdf")

        with closing(engine.open_document(source)) as document:
            images = document.images_on_page(0)

        assert len(images) == 1
        image = images[0]
        assert image.image_id
        assert image.page_index == 0
        assert image.rect.x0 == pytest.approx(72.0)
        assert image.rect.y0 == pytest.approx(72.0)
        assert image.rect.x1 == pytest.approx(272.0)
        assert image.rect.y1 == pytest.approx(172.0)
        assert image.pixel_width == 200
        assert image.pixel_height == 100
        assert image.is_shared is False

    def test_detecta_imagenes_compartidas(self, engine: PyMuPDFEngine, tmp_path: Path) -> None:
        source = synthetic.make_image_pdf(tmp_path / "compartida.pdf", pages=2)

        with closing(engine.open_document(source)) as document:
            first = document.images_on_page(0)
            second = document.images_on_page(1)

        assert first[0].image_id == second[0].image_id
        assert first[0].used_on_pages == (0, 1)
        assert first[0].is_shared is True

    def test_una_pagina_sin_imagenes(self, engine: PyMuPDFEngine, tmp_path: Path) -> None:
        source = synthetic.make_text_pdf(tmp_path / "texto.pdf")

        with closing(engine.open_document(source)) as document:
            assert document.images_on_page(0) == ()


class TestOperacionesDePaginas:
    def test_reordena_y_elimina_paginas(self, engine: PyMuPDFEngine, tmp_path: Path) -> None:
        source = synthetic.make_text_pdf(tmp_path / "original.pdf", pages=3)
        destination = tmp_path / "reordenado.pdf"

        export(engine, source, destination, PageArrangement(3, order=(2, 0)))

        texts = page_texts(destination)
        assert len(texts) == 2
        assert "página 3" in texts[0]
        assert "página 1" in texts[1]

    def test_rotacion_adicional(self, engine: PyMuPDFEngine, tmp_path: Path) -> None:
        source = synthetic.make_text_pdf(tmp_path / "original.pdf", pages=2)
        destination = tmp_path / "rotado.pdf"

        export(
            engine,
            source,
            destination,
            PageArrangement(2, order=(0, 1), rotations={1: 90}),
        )

        with pymupdf.open(destination) as document:
            assert document.load_page(0).rotation == 0
            rotated = document.load_page(1)
            assert rotated.rotation == 90
            assert rotated.rect.width == pytest.approx(synthetic.A4_HEIGHT)

    def test_extraer_paginas_conserva_el_orden(self, engine: PyMuPDFEngine, tmp_path: Path) -> None:
        source = synthetic.make_text_pdf(tmp_path / "original.pdf", pages=3)
        destination = tmp_path / "extracto.pdf"

        export(engine, source, destination, PageArrangement.initial(3).subset([2, 1]))

        texts = page_texts(destination)
        assert len(texts) == 2
        assert "página 3" in texts[0]
        assert "página 2" in texts[1]

    def test_las_paginas_eliminadas_no_reciben_objetos_nuevos(
        self, engine: PyMuPDFEngine, tmp_path: Path
    ) -> None:
        """Los objetos de páginas eliminadas se ignoran sin romper la exportación."""
        source = synthetic.make_text_pdf(tmp_path / "original.pdf", pages=2)
        destination = tmp_path / "sin_pagina.pdf"
        text = TextObject(
            object_id="texto-1",
            page_index=1,
            rect=PdfRect(60, 200, 400, 240),
            text="NO DEBE APARECER",
        )
        with closing(engine.open_document(source)) as document:
            ExportDocument()(
                document,
                destination,
                objects=(text,),
                arrangement=PageArrangement(2, order=(0,)),
            )

        texts = page_texts(destination)
        assert len(texts) == 1
        assert "NO DEBE APARECER" not in texts[0]

    def test_el_parser_de_seleccion_alimenta_la_extraccion(
        self, engine: PyMuPDFEngine, tmp_path: Path
    ) -> None:
        source = synthetic.make_text_pdf(tmp_path / "original.pdf", pages=4)
        destination = tmp_path / "seleccion.pdf"
        selected = parse_page_selection("1, 3-4", 4)

        export(engine, source, destination, PageArrangement.initial(4).subset(selected))

        texts = page_texts(destination)
        assert len(texts) == 3
        assert "página 1" in texts[0]
        assert "página 3" in texts[1]
        assert "página 4" in texts[2]


class TestReemplazoDeImagen:
    def test_reemplaza_la_imagen_conservando_la_region(
        self, engine: PyMuPDFEngine, tmp_path: Path
    ) -> None:
        source = synthetic.make_image_pdf(tmp_path / "original.pdf")
        destination = tmp_path / "reemplazada.pdf"

        with closing(engine.open_document(source)) as document:
            image = document.images_on_page(0)[0]
            replacement = ImageReplacementObject(
                object_id="reemplazo-1",
                page_index=0,
                image_id=image.image_id,
                rect=image.rect,
                data=png_bytes((0.0, 0.0, 1.0)),
                mime_type="image/png",
            )
            result = ExportDocument()(
                document,
                destination,
                objects=(replacement,),
                arrangement=PageArrangement.initial(1),
            )

        assert result.replacement_count == 1
        with pymupdf.open(destination) as exported:
            page = exported.load_page(0)
            pixmap = page.get_pixmap(alpha=False)
            # Centro de la imagen original (72, 72)-(272, 172).
            red, green, blue = pixmap.pixel(172, 122)
        assert blue > 200
        assert red < 60
        assert green < 60

    def test_el_reemplazo_no_modifica_el_original(
        self, engine: PyMuPDFEngine, tmp_path: Path
    ) -> None:
        source = synthetic.make_image_pdf(tmp_path / "original.pdf")
        original = source.read_bytes()
        destination = tmp_path / "reemplazada.pdf"

        with closing(engine.open_document(source)) as document:
            image = document.images_on_page(0)[0]
            replacement = ImageReplacementObject(
                object_id="reemplazo-1",
                page_index=0,
                image_id=image.image_id,
                rect=image.rect,
                data=png_bytes((0.0, 0.0, 1.0)),
                mime_type="image/png",
            )
            ExportDocument()(
                document,
                destination,
                objects=(replacement,),
                arrangement=PageArrangement.initial(1),
            )

        assert source.read_bytes() == original
