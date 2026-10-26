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
import os
import tempfile
import threading
from collections.abc import Iterable, Mapping
from contextlib import suppress
from pathlib import Path
from typing import Any, Final, cast

import pymupdf

from bene.application.ports.pdf_engine import RenderedPage
from bene.domain.editing import (
    SUPPORTED_FONTS,
    EditObject,
    ImageObject,
    RedactionObject,
    TextAlignment,
    TextObject,
)
from bene.domain.errors import (
    DocumentAccessError,
    DocumentClosedError,
    DocumentNotFoundError,
    EncryptedDocumentError,
    ExportError,
    PageOutOfRangeError,
    RenderError,
    UnsupportedDocumentError,
)
from bene.domain.models import VALID_ROTATIONS, DocumentInfo, PageInfo, PageKind, PdfRect

TEXT_CHAR_THRESHOLD: Final[int] = 20
"""A partir de este número de caracteres la página se considera de texto."""

SCANNED_COVERAGE_THRESHOLD: Final[float] = 0.5
"""Fracción de la página cubierta por imágenes para considerarla escaneada."""

MAX_RENDER_PIXELS: Final[int] = 40_000_000
"""Límite de píxeles por render (≈ 40 MP, unos 120 MB en RGB888)."""

# PyMuPDF 2.0 no declara estas constantes en sus anotaciones, aunque existen en
# tiempo de ejecución.
REDACT_IMAGE_PIXELS: Final[int] = cast(int, pymupdf.PDF_REDACT_IMAGE_PIXELS)  # type: ignore[attr-defined]
REDACT_LINE_ART_REMOVE_IF_TOUCHED: Final[int] = cast(
    int,
    pymupdf.PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED,  # type: ignore[attr-defined]
)
REDACT_TEXT_REMOVE: Final[int] = cast(int, pymupdf.PDF_REDACT_TEXT_REMOVE)  # type: ignore[attr-defined]
ANNOT_REDACT: Final[int] = cast(int, pymupdf.PDF_ANNOT_REDACT)  # type: ignore[attr-defined]


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


TEXT_ALIGNMENTS: Final[dict[TextAlignment, int]] = {
    TextAlignment.LEFT: pymupdf.TEXT_ALIGN_LEFT,
    TextAlignment.CENTER: pymupdf.TEXT_ALIGN_CENTER,
    TextAlignment.RIGHT: pymupdf.TEXT_ALIGN_RIGHT,
}


def _normalized_path(path: Path) -> str:
    return os.path.normcase(str(path.expanduser().resolve()))


def _visible_rect_to_page(page: pymupdf.Page, rect: PdfRect) -> pymupdf.Rect:
    """Convierte un rectángulo visible (tras ``/Rotate``) al espacio de la página.

    ``insert_textbox``, ``insert_image`` y ``add_redact_annot`` trabajan en las
    coordenadas sin rotar de la página; el lienzo y el modelo usan las visibles.
    """
    visible = pymupdf.Rect(rect.x0, rect.y0, rect.x1, rect.y1)
    return visible * page.derotation_matrix


def _hex_to_rgb(color: str) -> tuple[float, float, float]:
    value = color.lstrip("#")
    return (
        int(value[0:2], 16) / 255.0,
        int(value[2:4], 16) / 255.0,
        int(value[4:6], 16) / 255.0,
    )


def _insert_text(page: pymupdf.Page, obj: TextObject) -> None:
    font_name = obj.style.font_name if obj.style.font_name in SUPPORTED_FONTS else "Helvetica"
    remaining = page.insert_textbox(
        _visible_rect_to_page(page, obj.rect),
        obj.text,
        fontname=font_name,
        fontsize=obj.style.font_size,
        color=_hex_to_rgb(obj.style.color),
        align=TEXT_ALIGNMENTS[obj.style.alignment],
        rotate=(360 - page.rotation) % 360,
    )
    if remaining < 0:
        raise ExportError(f"El texto no cabe en su región de la página {obj.page_index + 1}")


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

    def export_to(self, destination: Path, *, objects: Iterable[EditObject]) -> None:
        target = destination.expanduser().absolute()
        items = tuple(objects)

        with self._lock:
            if self._closed:
                raise DocumentClosedError()
            self._validate_destination(target)
            self._write_export(target, items)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._document.close()

    def _validate_destination(self, target: Path) -> None:
        if _normalized_path(target) == _normalized_path(self._info.path):
            raise ExportError("El archivo de destino debe ser distinto del PDF original")
        if target.exists() and target.is_dir():
            raise ExportError("El destino es una carpeta; indica un nombre de archivo PDF")
        if not target.parent.is_dir():
            raise ExportError(f"No existe la carpeta de destino: {target.parent}")

    def _write_export(self, target: Path, objects: tuple[EditObject, ...]) -> None:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{target.stem}-",
            suffix=".pdf",
            dir=target.parent,
        )
        os.close(descriptor)
        temporary = Path(temporary_name)

        try:
            self._build_export(temporary, objects)
            self._validate_export(temporary)
            temporary.replace(target)
        except ExportError:
            raise
        except Exception as error:  # el motor y el sistema pueden fallar de muchas formas
            raise ExportError(f"No se pudo exportar el documento: {error}") from error
        finally:
            with suppress(OSError):
                temporary.unlink(missing_ok=True)

    def _build_export(self, temporary: Path, objects: tuple[EditObject, ...]) -> None:
        # PyMuPDF solo puede conservar la protección con la contraseña de
        # propietario. La aplicación no la pide ni la guarda, así que se
        # rechaza el caso de forma explícita en vez de exportar sin cifrar.
        if self._info.encrypted:
            raise ExportError(
                "No se puede exportar un PDF cifrado; guarda antes una copia sin protección"
            )

        # Se parte de una copia limpia del original: el documento abierto en el
        # visor nunca se modifica (RN-001).
        document = pymupdf.open(self._info.path)
        try:
            pages: dict[int, list[EditObject]] = {}
            for obj in objects:
                if not 0 <= obj.page_index < document.page_count:
                    raise ExportError(
                        f"El objeto {obj.object_id!r} apunta a una página que no existe"
                    )
                pages.setdefault(obj.page_index, []).append(obj)

            for page_index, page_objects in pages.items():
                page = document.load_page(page_index)
                redactions = [obj for obj in page_objects if isinstance(obj, RedactionObject)]
                if redactions:
                    for redaction in redactions:
                        page.add_redact_annot(
                            _visible_rect_to_page(page, redaction.rect),
                            fill=(0, 0, 0),
                        )
                    # Primero se elimina el contenido original; el texto y las
                    # imágenes nuevos se insertan después para permitir
                    # «redactar y escribir encima».
                    page.apply_redactions(
                        images=REDACT_IMAGE_PIXELS,
                        graphics=REDACT_LINE_ART_REMOVE_IF_TOUCHED,
                        text=REDACT_TEXT_REMOVE,
                    )

                for obj in page_objects:
                    if isinstance(obj, TextObject):
                        _insert_text(page, obj)
                    elif isinstance(obj, ImageObject):
                        page.insert_image(
                            _visible_rect_to_page(page, obj.rect),
                            stream=obj.data,
                            rotate=page.rotation,
                            keep_proportion=False,
                        )

            # `garbage=4` elimina objetos y recursos que ya no se referencian,
            # imprescindible para que el contenido redactado no quede en el
            # archivo (RNF-008).
            document.save(
                temporary,
                garbage=4,
                deflate=True,
            )
        finally:
            document.close()

    def _validate_export(self, temporary: Path) -> None:
        try:
            document = pymupdf.open(temporary)
        except Exception as error:
            raise ExportError("El archivo exportado no se pudo reabrir") from error

        try:
            if not document.is_pdf or document.page_count != self._info.page_count:
                raise ExportError("El archivo exportado no tiene el número de páginas esperado")
            for page_index in range(document.page_count):
                page = document.load_page(page_index)
                if page.rect.is_empty:
                    raise ExportError(
                        f"La página {page_index + 1} del archivo exportado no es válida"
                    )
                annotations = page.annots()
                if annotations is not None:
                    for annotation in annotations:
                        if annotation.type[0] == ANNOT_REDACT:
                            raise ExportError(
                                "El archivo exportado conserva anotaciones de redacción"
                            )
        finally:
            document.close()

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
