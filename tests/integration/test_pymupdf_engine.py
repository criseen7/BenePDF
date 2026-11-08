"""Pruebas de integración del adaptador de PyMuPDF con archivos reales."""

from __future__ import annotations

from contextlib import closing
from pathlib import Path

import pytest

from bene.application.ports.pdf_engine import OpenedDocument, PdfEngine, RenderedPage
from bene.domain.errors import (
    DocumentAccessError,
    DocumentClosedError,
    DocumentNotFoundError,
    EncryptedDocumentError,
    PageOutOfRangeError,
    RenderError,
    UnsupportedDocumentError,
)
from bene.domain.models import PageKind, PdfRect
from bene.infrastructure.pdf.pymupdf_engine import PyMuPDFEngine
from tests.integration import synthetic


@pytest.fixture
def engine() -> PyMuPDFEngine:
    return PyMuPDFEngine()


def test_el_adaptador_cumple_el_puerto(engine: PyMuPDFEngine, tmp_path: Path) -> None:
    port: PdfEngine = engine
    path = synthetic.make_text_pdf(tmp_path / "documento.pdf")

    with closing(port.open_document(path)) as document:
        assert isinstance(document, OpenedDocument)


class TestApertura:
    def test_pdf_de_texto(self, engine: PyMuPDFEngine, tmp_path: Path) -> None:
        path = synthetic.make_text_pdf(tmp_path / "informe.pdf", pages=3, title="Informe anual")

        with closing(engine.open_document(path)) as document:
            assert document.info.page_count == 3
            assert document.info.title == "Informe anual"
            assert document.info.file_size_bytes == path.stat().st_size
            assert document.info.encrypted is False
            assert document.info.path == path

    def test_titulo_desde_el_nombre_si_no_hay_metadatos(
        self, engine: PyMuPDFEngine, tmp_path: Path
    ) -> None:
        path = synthetic.make_text_pdf(tmp_path / "presupuesto.pdf")

        with closing(engine.open_document(path)) as document:
            assert document.info.title == "presupuesto"

    def test_nombre_con_espacios_y_unicode(self, engine: PyMuPDFEngine, tmp_path: Path) -> None:
        path = synthetic.make_text_pdf(tmp_path / "informe año ñ.pdf")

        with closing(engine.open_document(path)) as document:
            assert document.info.page_count == 1

    def test_ruta_inexistente(self, engine: PyMuPDFEngine, tmp_path: Path) -> None:
        with pytest.raises(DocumentNotFoundError):
            engine.open_document(tmp_path / "no-existe.pdf")

    def test_directorio(self, engine: PyMuPDFEngine, tmp_path: Path) -> None:
        with pytest.raises(DocumentAccessError):
            engine.open_document(tmp_path)

    def test_archivo_vacio(self, engine: PyMuPDFEngine, tmp_path: Path) -> None:
        path = tmp_path / "vacio.pdf"
        path.write_bytes(b"")

        with pytest.raises(UnsupportedDocumentError):
            engine.open_document(path)

    def test_archivo_corrupto(self, engine: PyMuPDFEngine, tmp_path: Path) -> None:
        path = synthetic.make_corrupt_file(tmp_path / "roto.pdf")

        with pytest.raises(UnsupportedDocumentError):
            engine.open_document(path)

    def test_archivo_que_no_es_pdf(self, engine: PyMuPDFEngine, tmp_path: Path) -> None:
        path = synthetic.make_plain_text_file(tmp_path / "nota.txt")

        with pytest.raises(UnsupportedDocumentError):
            engine.open_document(path)


class TestCifrado:
    def test_sin_contrasena(self, engine: PyMuPDFEngine, tmp_path: Path) -> None:
        path = synthetic.make_encrypted_pdf(tmp_path / "cifrado.pdf")

        with pytest.raises(EncryptedDocumentError) as excinfo:
            engine.open_document(path)

        assert excinfo.value.wrong_password is False

    def test_contrasena_incorrecta(self, engine: PyMuPDFEngine, tmp_path: Path) -> None:
        path = synthetic.make_encrypted_pdf(tmp_path / "cifrado.pdf")

        with pytest.raises(EncryptedDocumentError) as excinfo:
            engine.open_document(path, password="incorrecta")

        assert excinfo.value.wrong_password is True

    def test_contrasena_correcta(self, engine: PyMuPDFEngine, tmp_path: Path) -> None:
        path = synthetic.make_encrypted_pdf(tmp_path / "cifrado.pdf")

        with closing(engine.open_document(path, password="clave")) as document:
            assert document.info.encrypted is True
            assert document.info.page_count == 1
            assert document.page_info(0).kind is PageKind.TEXT


class TestPageInfo:
    def test_pagina_de_texto(self, engine: PyMuPDFEngine, tmp_path: Path) -> None:
        path = synthetic.make_text_pdf(tmp_path / "texto.pdf")

        with closing(engine.open_document(path)) as document:
            info = document.page_info(0)

            assert info.index == 0
            assert info.kind is PageKind.TEXT
            assert info.width == pytest.approx(595.0)
            assert info.height == pytest.approx(842.0)
            assert info.rotation == 0
            assert info.text_char_count > 0
            assert info.image_count == 0

    def test_pagina_escaneada(self, engine: PyMuPDFEngine, tmp_path: Path) -> None:
        path = synthetic.make_scanned_pdf(tmp_path / "escaneado.pdf")

        with closing(engine.open_document(path)) as document:
            info = document.page_info(0)

            assert info.kind is PageKind.SCANNED
            assert info.text_char_count == 0
            assert info.image_count >= 1

    def test_pagina_grafica(self, engine: PyMuPDFEngine, tmp_path: Path) -> None:
        path = synthetic.make_graphic_pdf(tmp_path / "grafico.pdf")

        with closing(engine.open_document(path)) as document:
            assert document.page_info(0).kind is PageKind.GRAPHIC

    def test_pagina_vacia(self, engine: PyMuPDFEngine, tmp_path: Path) -> None:
        path = synthetic.make_empty_pdf(tmp_path / "vacio.pdf")

        with closing(engine.open_document(path)) as document:
            assert document.page_info(0).kind is PageKind.EMPTY

    def test_pagina_rotada(self, engine: PyMuPDFEngine, tmp_path: Path) -> None:
        path = synthetic.make_rotated_pdf(tmp_path / "rotado.pdf", rotation=90)

        with closing(engine.open_document(path)) as document:
            info = document.page_info(0)

            # width/height son las dimensiones sin rotación; la rotación va aparte.
            assert info.rotation == 90
            assert info.width == pytest.approx(595.0)
            assert info.height == pytest.approx(842.0)
            assert info.rotated_size == pytest.approx((842.0, 595.0))

    @pytest.mark.parametrize("page_index", [-1, 1, 100])
    def test_pagina_fuera_de_rango(
        self, engine: PyMuPDFEngine, tmp_path: Path, page_index: int
    ) -> None:
        path = synthetic.make_text_pdf(tmp_path / "texto.pdf")

        with closing(engine.open_document(path)) as document, pytest.raises(PageOutOfRangeError):
            document.page_info(page_index)


class TestRender:
    def test_render_a_escala_uno(self, engine: PyMuPDFEngine, tmp_path: Path) -> None:
        path = synthetic.make_text_pdf(tmp_path / "texto.pdf")

        with closing(engine.open_document(path)) as document:
            render = document.render_page(0, scale=1.0)

            assert isinstance(render, RenderedPage)
            assert (render.width, render.height) == (595, 842)
            assert render.stride >= render.width * 3
            assert len(render.samples) == render.stride * render.height
            # El fondo de la página es blanco.
            assert render.samples[:3] == b"\xff\xff\xff"

    def test_render_a_escala_dos(self, engine: PyMuPDFEngine, tmp_path: Path) -> None:
        path = synthetic.make_text_pdf(tmp_path / "texto.pdf")

        with closing(engine.open_document(path)) as document:
            render = document.render_page(0, scale=2.0)

            assert (render.width, render.height) == (1190, 1684)

    @pytest.mark.parametrize(
        ("rotation", "expected"),
        [(90, (842, 595)), (180, (595, 842)), (270, (842, 595))],
    )
    def test_rotacion_de_vista(
        self,
        engine: PyMuPDFEngine,
        tmp_path: Path,
        rotation: int,
        expected: tuple[int, int],
    ) -> None:
        path = synthetic.make_text_pdf(tmp_path / "texto.pdf")

        with closing(engine.open_document(path)) as document:
            render = document.render_page(0, scale=1.0, rotation=rotation)

            assert (render.width, render.height) == expected
            assert render.rotation == rotation

    def test_pagina_rotada_en_el_archivo(self, engine: PyMuPDFEngine, tmp_path: Path) -> None:
        path = synthetic.make_rotated_pdf(tmp_path / "rotado.pdf", rotation=90)

        with closing(engine.open_document(path)) as document:
            render = document.render_page(0, scale=1.0)

            assert (render.width, render.height) == (842, 595)

    def test_rotacion_del_archivo_mas_rotacion_de_vista(
        self, engine: PyMuPDFEngine, tmp_path: Path
    ) -> None:
        path = synthetic.make_rotated_pdf(tmp_path / "rotado.pdf", rotation=90)

        with closing(engine.open_document(path)) as document:
            render = document.render_page(0, scale=1.0, rotation=90)

            assert (render.width, render.height) == (595, 842)

    def test_limite_de_pixeles(self, engine: PyMuPDFEngine, tmp_path: Path) -> None:
        path = synthetic.make_text_pdf(tmp_path / "texto.pdf")

        with (
            closing(engine.open_document(path)) as document,
            pytest.raises(RenderError, match="límite"),
        ):
            document.render_page(0, scale=10.0)

    def test_escala_invalida(self, engine: PyMuPDFEngine, tmp_path: Path) -> None:
        path = synthetic.make_text_pdf(tmp_path / "texto.pdf")

        with (
            closing(engine.open_document(path)) as document,
            pytest.raises(ValueError, match="Escala"),
        ):
            document.render_page(0, scale=0.0)

    def test_rotacion_invalida(self, engine: PyMuPDFEngine, tmp_path: Path) -> None:
        path = synthetic.make_text_pdf(tmp_path / "texto.pdf")

        with (
            closing(engine.open_document(path)) as document,
            pytest.raises(ValueError, match="Rotación"),
        ):
            document.render_page(0, scale=1.0, rotation=45)


class TestMedicionDeTexto:
    def test_un_texto_corto_cabe(self, engine: PyMuPDFEngine, tmp_path: Path) -> None:
        path = synthetic.make_text_pdf(tmp_path / "texto.pdf")

        with closing(engine.open_document(path)) as document:
            measurement = document.measure_text(
                0,
                text="Hola",
                rect=PdfRect(50, 50, 300, 100),
                font_name="Helvetica",
                font_size=12,
            )

        assert measurement.fits is True
        assert measurement.overflow_points == 0
        assert measurement.unsupported == ()

    def test_un_texto_largo_no_cabe(self, engine: PyMuPDFEngine, tmp_path: Path) -> None:
        path = synthetic.make_text_pdf(tmp_path / "texto.pdf")

        with closing(engine.open_document(path)) as document:
            measurement = document.measure_text(
                0,
                text="X" * 500,
                rect=PdfRect(50, 50, 120, 70),
                font_name="Helvetica",
                font_size=14,
            )

        assert measurement.fits is False
        assert measurement.overflow_points > 0

    def test_detecta_caracteres_sin_glifo(self, engine: PyMuPDFEngine, tmp_path: Path) -> None:
        path = synthetic.make_text_pdf(tmp_path / "texto.pdf")

        with closing(engine.open_document(path)) as document:
            measurement = document.measure_text(
                0,
                text="Hola 🙂",
                rect=PdfRect(50, 50, 300, 100),
                font_name="Helvetica",
                font_size=12,
            )

        assert measurement.fits is False
        assert "🙂" in measurement.unsupported

    def test_conserva_el_euro(self, engine: PyMuPDFEngine, tmp_path: Path) -> None:
        path = synthetic.make_text_pdf(tmp_path / "texto.pdf")

        with closing(engine.open_document(path)) as document:
            measurement = document.measure_text(
                0,
                text="Precio: 10 €",
                rect=PdfRect(50, 50, 300, 100),
                font_name="Helvetica",
                font_size=12,
            )

        assert measurement.fits is True
        assert measurement.unsupported == ()


class TestCierre:
    def test_cerrar_dos_veces(self, engine: PyMuPDFEngine, tmp_path: Path) -> None:
        path = synthetic.make_text_pdf(tmp_path / "texto.pdf")
        document = engine.open_document(path)

        document.close()
        document.close()

        with pytest.raises(DocumentClosedError):
            document.page_info(0)

    def test_no_permite_renderizar_tras_cerrar(self, engine: PyMuPDFEngine, tmp_path: Path) -> None:
        path = synthetic.make_text_pdf(tmp_path / "texto.pdf")
        document = engine.open_document(path)
        document.close()

        with pytest.raises(DocumentClosedError):
            document.render_page(0, scale=1.0)
