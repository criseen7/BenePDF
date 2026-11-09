"""Pruebas de documentos grandes (RNF-001, RNF-003).

Se marcan como ``slow`` y no forman parte de la suite rápida. Generan los PDFs
en tiempo de ejecución para no guardar binarios en el repositorio.
"""

from __future__ import annotations

from contextlib import closing
from pathlib import Path

import pymupdf
import pytest

from bene.application.use_cases.open_document import OpenDocument
from bene.application.use_cases.render_page import RenderPage
from bene.domain.models import PageKind
from bene.infrastructure.pdf.pymupdf_engine import PyMuPDFEngine

pytestmark = pytest.mark.slow

PAGE_COUNT = 100
A4_WIDTH = 595.0
A4_HEIGHT = 842.0


@pytest.fixture
def engine() -> PyMuPDFEngine:
    return PyMuPDFEngine()


def make_text_document(path: Path, pages: int = PAGE_COUNT) -> Path:
    document = pymupdf.open()
    for index in range(pages):
        page = document.new_page(width=A4_WIDTH, height=A4_HEIGHT)
        page.insert_text((72, 100), f"Documento grande, página {index + 1}", fontsize=12)
        for line in range(20):
            page.insert_text(
                (72, 130 + line * 16),
                f"Línea {line + 1} de contenido seleccionable de prueba.",
                fontsize=10,
            )
    document.save(path, garbage=4, deflate=True)
    document.close()
    return path


def make_scanned_document(path: Path, pages: int = PAGE_COUNT) -> Path:
    source = pymupdf.open()
    source_page = source.new_page(width=A4_WIDTH, height=A4_HEIGHT)
    source_page.draw_rect(source_page.rect, color=(0.85, 0.85, 0.85), fill=(0.95, 0.95, 0.95))
    source_page.insert_text((72, 100), "Escaneo de prueba", fontsize=14)
    pixmap = source_page.get_pixmap(dpi=60, alpha=False)
    source.close()

    document = pymupdf.open()
    for _ in range(pages):
        page = document.new_page(width=A4_WIDTH, height=A4_HEIGHT)
        page.insert_image(page.rect, pixmap=pixmap)
    document.save(path, garbage=4, deflate=True)
    document.close()
    return path


class TestDocumentoGrandeDeTexto:
    def test_abre_clasifica_y_renderiza_los_extremos(
        self, engine: PyMuPDFEngine, tmp_path: Path
    ) -> None:
        path = make_text_document(tmp_path / "grande-texto.pdf")

        with closing(OpenDocument(engine)(path)) as document:
            assert document.info.page_count == PAGE_COUNT
            assert document.info.file_size_bytes > 0

            first = document.page_info(0)
            last = document.page_info(PAGE_COUNT - 1)
            assert first.kind is PageKind.TEXT
            assert last.kind is PageKind.TEXT
            assert first.text_char_count > 0
            assert last.text_char_count > 0

            renderer = RenderPage(document)
            first_image = renderer(0, scale=1.0)
            last_image = renderer(PAGE_COUNT - 1, scale=1.0)
            assert first_image.page_index == 0
            assert last_image.page_index == PAGE_COUNT - 1
            assert first_image.width == round(A4_WIDTH)
            assert first_image.height == round(A4_HEIGHT)
            assert len(first_image.samples) == first_image.stride * first_image.height
            assert len(last_image.samples) == last_image.stride * last_image.height


class TestDocumentoGrandeEscaneado:
    def test_abre_clasifica_y_renderiza_los_extremos(
        self, engine: PyMuPDFEngine, tmp_path: Path
    ) -> None:
        path = make_scanned_document(tmp_path / "grande-escaneado.pdf")

        with closing(OpenDocument(engine)(path)) as document:
            assert document.info.page_count == PAGE_COUNT

            first = document.page_info(0)
            last = document.page_info(PAGE_COUNT - 1)
            assert first.kind is PageKind.SCANNED
            assert last.kind is PageKind.SCANNED
            assert first.image_count == 1
            assert last.image_count == 1

            renderer = RenderPage(document)
            first_image = renderer(0, scale=0.5)
            last_image = renderer(PAGE_COUNT - 1, scale=0.5)
            assert first_image.width == round(A4_WIDTH * 0.5)
            assert last_image.width == round(A4_WIDTH * 0.5)
            # Un escaneo real no es una imagen en blanco.
            assert set(first_image.samples) != {0xFF}
            assert set(last_image.samples) != {0xFF}
