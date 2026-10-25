"""Pruebas de la clasificación de páginas y de la cobertura de imágenes."""

from __future__ import annotations

import pymupdf
import pytest

from bene.domain.models import PageKind
from bene.infrastructure.pdf.pymupdf_engine import (
    SCANNED_COVERAGE_THRESHOLD,
    TEXT_CHAR_THRESHOLD,
    classify_page,
    image_coverage,
)


class TestClassifyPage:
    def test_texto_suficiente(self) -> None:
        kind = classify_page(
            text_char_count=TEXT_CHAR_THRESHOLD,
            image_coverage=1.0,
            has_images=True,
            has_drawings=True,
        )

        assert kind is PageKind.TEXT

    def test_imagen_a_pagina_completa_sin_texto_es_escaneada(self) -> None:
        kind = classify_page(
            text_char_count=0,
            image_coverage=SCANNED_COVERAGE_THRESHOLD,
            has_images=True,
            has_drawings=False,
        )

        assert kind is PageKind.SCANNED

    def test_escaneo_con_texto_residual(self) -> None:
        kind = classify_page(
            text_char_count=5,
            image_coverage=0.9,
            has_images=True,
            has_drawings=False,
        )

        assert kind is PageKind.SCANNED

    def test_poco_texto_sin_imagen_sigue_siendo_texto(self) -> None:
        kind = classify_page(
            text_char_count=5,
            image_coverage=0.1,
            has_images=True,
            has_drawings=False,
        )

        assert kind is PageKind.TEXT

    @pytest.mark.parametrize(("has_images", "has_drawings"), [(True, False), (False, True)])
    def test_contenido_grafico(self, has_images: bool, has_drawings: bool) -> None:
        kind = classify_page(
            text_char_count=0,
            image_coverage=0.2,
            has_images=has_images,
            has_drawings=has_drawings,
        )

        assert kind is PageKind.GRAPHIC

    def test_pagina_vacia(self) -> None:
        kind = classify_page(
            text_char_count=0,
            image_coverage=0.0,
            has_images=False,
            has_drawings=False,
        )

        assert kind is PageKind.EMPTY


class TestImageCoverage:
    def test_imagen_que_cubre_la_pagina(self) -> None:
        page = pymupdf.Rect(0, 0, 100, 200)

        coverage = image_coverage(page, [{"bbox": (0, 0, 100, 200)}])

        assert coverage == 1.0

    def test_imagen_parcial(self) -> None:
        page = pymupdf.Rect(0, 0, 100, 200)

        coverage = image_coverage(page, [{"bbox": (0, 0, 100, 50)}])

        assert coverage == pytest.approx(0.25)

    def test_recorta_al_area_de_la_pagina(self) -> None:
        page = pymupdf.Rect(0, 0, 100, 100)

        coverage = image_coverage(page, [{"bbox": (-100, -100, 200, 200)}])

        assert coverage == 1.0

    def test_varias_imagenes_no_superan_uno(self) -> None:
        page = pymupdf.Rect(0, 0, 100, 100)

        coverage = image_coverage(
            page,
            [{"bbox": (0, 0, 100, 100)}, {"bbox": (0, 0, 100, 100)}],
        )

        assert coverage == 1.0

    @pytest.mark.parametrize("bbox", [None, (0, 0, 10), "no-es-un-rect", (0, 0, "x", 10)])
    def test_ignora_bbox_invalido(self, bbox: object) -> None:
        page = pymupdf.Rect(0, 0, 100, 100)

        assert image_coverage(page, [{"bbox": bbox}]) == 0.0

    def test_pagina_sin_area(self) -> None:
        assert image_coverage(pymupdf.Rect(0, 0, 0, 0), [{"bbox": (0, 0, 10, 10)}]) == 0.0
