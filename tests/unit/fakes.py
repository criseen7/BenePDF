"""Dobles de prueba para los puertos, sin Qt ni motor PDF real."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path

from bene.application.ports.pdf_engine import (
    EmbeddedImage,
    RenderedPage,
    SearchMatch,
    TextMeasurement,
)
from bene.domain.editing import EditObject, TextAlignment
from bene.domain.errors import ExportError, PageOutOfRangeError
from bene.domain.models import VALID_ROTATIONS, DocumentInfo, PageInfo, PageKind, PdfRect
from bene.domain.pages import PageArrangement


class FakeDocument:
    """Sesión falsa con una imagen blanca por página."""

    def __init__(self, info: DocumentInfo, pages: Sequence[PageInfo]) -> None:
        self._info = info
        self._pages = tuple(pages)
        self.closed = False
        self.render_calls: list[tuple[int, float, int]] = []
        self.export_calls: list[tuple[Path, tuple[EditObject, ...]]] = []
        self.export_arrangements: list[PageArrangement | None] = []
        self.search_calls: list[str] = []
        self.search_results: tuple[SearchMatch, ...] = ()
        self.page_images: dict[int, tuple[EmbeddedImage, ...]] = {}
        self.export_should_fail = False

    @property
    def info(self) -> DocumentInfo:
        return self._info

    def page_info(self, page_index: int) -> PageInfo:
        if not 0 <= page_index < len(self._pages):
            raise PageOutOfRangeError(page_index, len(self._pages))
        return self._pages[page_index]

    def page_size(self, page_index: int) -> tuple[float, float]:
        return self.page_info(page_index).rotated_size

    def search_text(self, query: str) -> tuple[SearchMatch, ...]:
        self.search_calls.append(query)
        return self.search_results

    def images_on_page(self, page_index: int) -> tuple[EmbeddedImage, ...]:
        self.page_info(page_index)
        return self.page_images.get(page_index, ())

    def render_page(self, page_index: int, *, scale: float, rotation: int = 0) -> RenderedPage:
        page = self.page_info(page_index)
        if scale <= 0:
            raise ValueError(f"Escala inválida: {scale}")
        if rotation not in VALID_ROTATIONS:
            raise ValueError(f"Rotación inválida: {rotation}")

        width_pt, height_pt = page.rotated_size
        if rotation in (90, 270):
            width_pt, height_pt = height_pt, width_pt

        self.render_calls.append((page_index, scale, rotation))
        width = max(1, round(width_pt * scale))
        height = max(1, round(height_pt * scale))
        stride = width * 3
        return RenderedPage(
            page_index=page_index,
            width=width,
            height=height,
            stride=stride,
            samples=b"\xff" * (stride * height),
            scale=scale,
            rotation=rotation,
        )

    def close(self) -> None:
        self.closed = True

    def export_to(
        self,
        destination: Path,
        *,
        objects: Iterable[EditObject],
        arrangement: PageArrangement | None = None,
    ) -> None:
        if self.export_should_fail:
            raise ExportError("Fallo de exportación simulado")
        self.export_calls.append((destination, tuple(objects)))
        self.export_arrangements.append(arrangement)
        destination.write_bytes(b"%PDF-1.7 exportacion falsa")

    def measure_text(
        self,
        page_index: int,
        *,
        text: str,
        rect: PdfRect,
        font_name: str,
        font_size: float,
        alignment: TextAlignment = TextAlignment.LEFT,
    ) -> TextMeasurement:
        self.page_info(page_index)
        line_height = font_size * 1.2
        chars_per_line = max(1, int(rect.width // (font_size * 0.5)))
        lines_capacity = max(1, int(rect.height // line_height))
        needed_lines = max(1, -(-len(text) // chars_per_line))
        fits = needed_lines <= lines_capacity
        overflow = max(0.0, (needed_lines - lines_capacity) * line_height)
        return TextMeasurement(fits=fits, overflow_points=overflow)


class FakePdfEngine:
    """Motor falso que abre siempre el mismo documento."""

    def __init__(
        self,
        pages: Sequence[PageInfo],
        *,
        title: str = "Documento de prueba",
        encrypted: bool = False,
    ) -> None:
        self._pages = tuple(pages)
        self._title = title
        self._encrypted = encrypted
        self.opened: list[tuple[Path, str | None]] = []
        self.documents: list[FakeDocument] = []

    def open_document(self, path: Path, *, password: str | None = None) -> FakeDocument:
        self.opened.append((path, password))
        info = DocumentInfo(
            path=path,
            page_count=len(self._pages),
            file_size_bytes=1024,
            metadata={"title": self._title},
            encrypted=self._encrypted,
        )
        document = FakeDocument(info, self._pages)
        self.documents.append(document)
        return document


def make_pages(count: int = 3, *, kind: PageKind = PageKind.TEXT) -> tuple[PageInfo, ...]:
    """Genera páginas A4 consecutivas para las pruebas."""
    return tuple(
        PageInfo(index=index, width=595.0, height=842.0, kind=kind, text_char_count=100)
        for index in range(count)
    )
