"""Pruebas de los modelos de dominio."""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from bene.domain.errors import InvalidGeometryError
from bene.domain.models import DocumentInfo, PageInfo, PageKind, PdfRect


class TestPdfRect:
    def test_calcula_dimensiones_y_area(self) -> None:
        rect = PdfRect(x0=10.0, y0=20.0, x1=110.0, y1=70.0)

        assert rect.width == 100.0
        assert rect.height == 50.0
        assert rect.area == 5000.0
        assert not rect.is_empty

    def test_from_size(self) -> None:
        rect = PdfRect.from_size(200.0, 100.0, x=5.0, y=7.0)

        assert rect.to_tuple() == (5.0, 7.0, 205.0, 107.0)

    def test_rectangulo_de_area_cero_es_vacio(self) -> None:
        assert PdfRect.from_size(100.0, 0.0).is_empty

    def test_translated_no_muta_el_original(self) -> None:
        original = PdfRect(0.0, 0.0, 10.0, 10.0)

        movido = original.translated(5.0, -2.0)

        assert original.to_tuple() == (0.0, 0.0, 10.0, 10.0)
        assert movido.to_tuple() == (5.0, -2.0, 15.0, 8.0)

    @pytest.mark.parametrize(("x", "y"), [(0.0, 0.0), (5.0, 5.0), (10.0, 10.0), (0.0, 10.0)])
    def test_contains_incluye_los_bordes(self, x: float, y: float) -> None:
        assert PdfRect(0.0, 0.0, 10.0, 10.0).contains(x, y)

    @pytest.mark.parametrize(("x", "y"), [(-0.1, 5.0), (10.1, 5.0), (5.0, -0.1), (5.0, 10.1)])
    def test_contains_excluye_el_exterior(self, x: float, y: float) -> None:
        assert not PdfRect(0.0, 0.0, 10.0, 10.0).contains(x, y)

    def test_rechaza_coordenadas_invertidas(self) -> None:
        with pytest.raises(InvalidGeometryError, match="invertidas"):
            PdfRect(x0=10.0, y0=0.0, x1=5.0, y1=10.0)

    @pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
    def test_rechaza_coordenadas_no_finitas(self, value: float) -> None:
        with pytest.raises(InvalidGeometryError, match="finitas"):
            PdfRect(x0=0.0, y0=0.0, x1=value, y1=10.0)


class TestPageInfo:
    def test_tamano_con_rotacion(self) -> None:
        vertical = PageInfo(index=0, width=595.0, height=842.0)
        girada = PageInfo(index=0, width=595.0, height=842.0, rotation=90)

        assert vertical.rotated_size == (595.0, 842.0)
        assert girada.rotated_size == (842.0, 595.0)

    @pytest.mark.parametrize("rotation", [45, 360, -90])
    def test_rechaza_rotaciones_no_soportadas(self, rotation: int) -> None:
        with pytest.raises(ValueError, match="Rotación"):
            PageInfo(index=0, width=100.0, height=100.0, rotation=rotation)

    def test_rechaza_indice_negativo(self) -> None:
        with pytest.raises(ValueError, match="negativo"):
            PageInfo(index=-1, width=100.0, height=100.0)

    def test_rechaza_dimensiones_invalidas(self) -> None:
        with pytest.raises(InvalidGeometryError):
            PageInfo(index=0, width=0.0, height=100.0)

    def test_rechaza_recuentos_negativos(self) -> None:
        with pytest.raises(ValueError, match="recuentos"):
            PageInfo(index=0, width=100.0, height=100.0, image_count=-1)

    def test_valor_por_defecto_vacia(self) -> None:
        assert PageInfo(index=0, width=100.0, height=100.0).kind is PageKind.EMPTY


class TestDocumentInfo:
    def test_titulo_desde_metadatos(self) -> None:
        info = DocumentInfo(
            path=Path("contrato.pdf"),
            page_count=2,
            file_size_bytes=100,
            metadata={"title": "Contrato de alquiler"},
        )

        assert info.title == "Contrato de alquiler"

    def test_titulo_desde_el_nombre_si_falta_el_metadato(self) -> None:
        info = DocumentInfo(path=Path("contrato.pdf"), page_count=2, file_size_bytes=100)

        assert info.title == "contrato"

    def test_titulo_en_blanco_usa_el_nombre(self) -> None:
        info = DocumentInfo(
            path=Path("factura.pdf"),
            page_count=1,
            file_size_bytes=100,
            metadata={"title": "   "},
        )

        assert info.title == "factura"

    def test_rechaza_documento_sin_paginas(self) -> None:
        with pytest.raises(ValueError, match="al menos una página"):
            DocumentInfo(path=Path("vacio.pdf"), page_count=0, file_size_bytes=0)

    def test_rechaza_tamano_negativo(self) -> None:
        with pytest.raises(ValueError, match="tamaño"):
            DocumentInfo(path=Path("x.pdf"), page_count=1, file_size_bytes=-1)

    def test_es_inmutable(self) -> None:
        info = DocumentInfo(path=Path("x.pdf"), page_count=1, file_size_bytes=10)

        with pytest.raises(AttributeError):
            info.page_count = 2  # type: ignore[misc]
