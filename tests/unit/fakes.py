"""Dobles de prueba para los puertos, sin Qt ni motor PDF real."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from bene.application.ports.pdf_engine import RenderedPage
from bene.domain.errors import PageOutOfRangeError
from bene.domain.models import VALID_ROTATIONS, DocumentInfo, PageInfo, PageKind


class FakeDocument:
    """Sesión falsa con una imagen blanca por página."""

    def __init__(self, info: DocumentInfo, pages: Sequence[PageInfo]) -> None:
        self._info = info
        self._pages = tuple(pages)
        self.closed = False
        self.render_calls: list[tuple[int, float, int]] = []

    @property
    def info(self) -> DocumentInfo:
        return self._info

    def page_info(self, page_index: int) -> PageInfo:
        if not 0 <= page_index < len(self._pages):
            raise PageOutOfRangeError(page_index, len(self._pages))
        return self._pages[page_index]

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


class FakePdfEngine:
    """Motor falso que abre siempre el mismo documento."""

    def __init__(self, pages: Sequence[PageInfo], *, title: str = "Documento de prueba") -> None:
        self._pages = tuple(pages)
        self._title = title
        self.opened: list[tuple[Path, str | None]] = []

    def open_document(self, path: Path, *, password: str | None = None) -> FakeDocument:
        self.opened.append((path, password))
        info = DocumentInfo(
            path=path,
            page_count=len(self._pages),
            file_size_bytes=1024,
            metadata={"title": self._title},
        )
        return FakeDocument(info, self._pages)


def make_pages(count: int = 3, *, kind: PageKind = PageKind.TEXT) -> tuple[PageInfo, ...]:
    """Genera páginas A4 consecutivas para las pruebas."""
    return tuple(
        PageInfo(index=index, width=595.0, height=842.0, kind=kind, text_char_count=100)
        for index in range(count)
    )
