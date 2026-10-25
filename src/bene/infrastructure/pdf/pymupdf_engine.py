"""Adaptador de PyMuPDF para el puerto :class:`~bene.application.ports.pdf_engine.PdfEngine`.

Es el único módulo de la aplicación que importa ``pymupdf``. Su
responsabilidad es traducir entre el modelo del dominio y la biblioteca, y
convertir los fallos de MuPDF en errores tipados.

PyMuPDF no es seguro para uso concurrente, así que cada sesión serializa el
acceso al documento con un cerrojo. Los renders de una misma sesión se
ejecutan de uno en uno; el visor puede pedirlos desde un hilo de trabajo.
"""

from __future__ import annotations

import math
import threading
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, Final

import pymupdf

from bene.application.ports.pdf_engine import RenderedPage
from bene.domain.errors import (
    DocumentAccessError,
    DocumentClosedError,
    DocumentNotFoundError,
    EncryptedDocumentError,
    PageOutOfRangeError,
    RenderError,
    UnsupportedDocumentError,
)
from bene.domain.models import VALID_ROTATIONS, DocumentInfo, PageInfo, PageKind

TEXT_CHAR_THRESHOLD: Final[int] = 20
"""A partir de este número de caracteres la página se considera de texto."""

SCANNED_COVERAGE_THRESHOLD: Final[float] = 0.5
"""Fracción de la página cubierta por imágenes para considerarla escaneada."""

MAX_RENDER_PIXELS: Final[int] = 40_000_000
"""Límite de píxeles por render (≈ 40 MP, unos 120 MB en RGB888)."""


def classify_page(
    *,
    text_char_count: int,
    image_coverage: float,
    has_images: bool,
    has_drawings: bool,
) -> PageKind:
    """Clasificación orientativa de una página (RF-005).

    La regla es deliberadamente simple y explicable: texto suficiente manda;
    si no, una imagen que cubre la página indica un escaneo; si hay algo
    gráfico, ``GRAPHIC``; y sin contenido, ``EMPTY``.
    """
    if text_char_count >= TEXT_CHAR_THRESHOLD:
        return PageKind.TEXT
    if image_coverage >= SCANNED_COVERAGE_THRESHOLD:
        return PageKind.SCANNED
    if text_char_count > 0:
        return PageKind.TEXT
    if has_images or has_drawings:
        return PageKind.GRAPHIC
    return PageKind.EMPTY


def image_coverage(page_rect: pymupdf.Rect, images: Iterable[Mapping[str, Any]]) -> float:
    """Proporción de la página cubierta por imágenes, recortada a 1.0."""
    area = page_rect.get_area()
    if area <= 0:
        return 0.0

    covered = 0.0
    for image in images:
        bbox = image.get("bbox")
        if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
            continue
        try:
            x0, y0, x1, y1 = (float(value) for value in bbox)
            image_rect = pymupdf.Rect(x0, y0, x1, y1)
        except (TypeError, ValueError):
            continue
        intersection = image_rect.intersect(page_rect)
        if not intersection.is_empty:
            covered += intersection.get_area()
    return min(covered / area, 1.0)


class PyMuPDFEngine:
    """Fábrica de sesiones PyMuPDF. No mantiene estado entre documentos."""

    def open_document(self, path: Path, *, password: str | None = None) -> PyMuPDFDocument:
        absolute = path.expanduser().absolute()

        if not absolute.exists():
            raise DocumentNotFoundError(absolute)
        if not absolute.is_file():
            raise DocumentAccessError(absolute)

        document = self._open(absolute)

        try:
            return self._build_session(document, absolute, password)
        except BaseException:
            # Cualquier fallo posterior a la apertura debe liberar el documento,
            # incluso si es un error de programación.
            document.close()
            raise

    @staticmethod
    def _open(path: Path) -> pymupdf.Document:
        try:
            return pymupdf.open(path)
        except FileNotFoundError as error:
            raise DocumentNotFoundError(path) from error
        except PermissionError as error:
            raise DocumentAccessError(path) from error
        except (pymupdf.FileDataError, pymupdf.EmptyFileError) as error:
            raise UnsupportedDocumentError(path) from error
        except RuntimeError as error:
            # MuPDF lanza RuntimeError para ficheros malformados o truncados.
            raise UnsupportedDocumentError(path) from error
        except OSError as error:
            raise DocumentAccessError(path) from error

    @staticmethod
    def _build_session(
        document: pymupdf.Document, path: Path, password: str | None
    ) -> PyMuPDFDocument:
        # PyMuPDF abre también imágenes, EPUB y texto plano; solo sirve un PDF.
        if not document.is_pdf:
            raise UnsupportedDocumentError(path)

        # Debe leerse antes de autenticar: tras `authenticate()` el motor deja
        # de marcar el documento como cifrado.
        encrypted = bool(document.is_encrypted or document.needs_pass)

        if document.needs_pass:
            if password is None:
                raise EncryptedDocumentError(path)
            if not document.authenticate(password):
                raise EncryptedDocumentError(path, wrong_password=True)

        if document.page_count < 1:
            raise UnsupportedDocumentError(path)

        info = DocumentInfo(
            path=path,
            page_count=document.page_count,
            file_size_bytes=PyMuPDFEngine._file_size(path),
            metadata=PyMuPDFEngine._metadata(document),
            encrypted=encrypted,
        )
        return PyMuPDFDocument(document, info)

    @staticmethod
    def _file_size(path: Path) -> int:
        try:
            return path.stat().st_size
        except OSError as error:
            raise DocumentAccessError(path) from error

    @staticmethod
    def _metadata(document: pymupdf.Document) -> dict[str, str]:
        metadata: dict[str, str] = {}
        for key, value in (document.metadata or {}).items():
            if isinstance(value, str) and value.strip():
                metadata[key] = value.strip()
        return metadata


class PyMuPDFDocument:
    """Sesión abierta. El llamador es responsable de llamar a :meth:`close`."""

    def __init__(self, document: pymupdf.Document, info: DocumentInfo) -> None:
        self._document = document
        self._info = info
        self._lock = threading.Lock()
        self._closed = False

    @property
    def info(self) -> DocumentInfo:
        return self._info

    def page_info(self, page_index: int) -> PageInfo:
        with self._lock:
            page = self._load_page(page_index)
            return self._build_page_info(page, page_index)

    def render_page(self, page_index: int, *, scale: float, rotation: int = 0) -> RenderedPage:
        if not math.isfinite(scale) or scale <= 0:
            raise ValueError(f"Escala inválida: {scale}")
        if rotation not in VALID_ROTATIONS:
            raise ValueError(f"Rotación de vista inválida: {rotation}")

        with self._lock:
            page = self._load_page(page_index)

            if page.rect.get_area() * scale * scale > MAX_RENDER_PIXELS:
                raise RenderError(
                    page_index,
                    "la resolución solicitada supera el límite de memoria",
                )

            try:
                matrix = pymupdf.Matrix(scale, scale)
                if rotation:
                    matrix = matrix.prerotate(rotation)
                pixmap = page.get_pixmap(matrix=matrix, alpha=False, colorspace=pymupdf.csRGB)
            except Exception as error:  # el motor puede fallar con cualquier formato
                raise RenderError(page_index, str(error) or type(error).__name__) from error

            if pixmap.n != 3:
                raise RenderError(page_index, f"formato de píxel inesperado ({pixmap.n} canales)")

            return RenderedPage(
                page_index=page_index,
                width=pixmap.width,
                height=pixmap.height,
                stride=pixmap.stride,
                samples=pixmap.samples,
                scale=scale,
                rotation=rotation,
            )

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._document.close()

    def _load_page(self, page_index: int) -> pymupdf.Page:
        if self._closed:
            raise DocumentClosedError()
        if not 0 <= page_index < self._document.page_count:
            raise PageOutOfRangeError(page_index, self._document.page_count)
        try:
            return self._document.load_page(page_index)
        except Exception as error:
            # Si una página concreta no se puede cargar, el documento está dañado.
            raise UnsupportedDocumentError(self._info.path) from error

    def _build_page_info(self, page: pymupdf.Page, page_index: int) -> PageInfo:
        rotation = page.rotation % 360
        if rotation not in VALID_ROTATIONS:
            rotation = 0

        rect = page.rect
        if rotation in (90, 270):
            width, height = rect.height, rect.width
        else:
            width, height = rect.width, rect.height

        text_char_count = len("".join(page.get_text("text").split()))
        images = page.get_image_info()
        coverage = image_coverage(rect, images)

        has_drawings = False
        if text_char_count == 0 and coverage < SCANNED_COVERAGE_THRESHOLD:
            has_drawings = bool(page.get_drawings())

        return PageInfo(
            index=page_index,
            width=width,
            height=height,
            rotation=rotation,
            kind=classify_page(
                text_char_count=text_char_count,
                image_coverage=coverage,
                has_images=bool(images),
                has_drawings=has_drawings,
            ),
            text_char_count=text_char_count,
            image_count=len(images),
        )
