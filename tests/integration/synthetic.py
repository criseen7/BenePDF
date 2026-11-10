"""PDFs sintéticos para las pruebas de integración.

Se generan en tiempo de ejecución: no se guardan binarios en el repositorio.
No contienen información personal.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pymupdf

A4_WIDTH = 595.0
A4_HEIGHT = 842.0

# Las anotaciones de PyMuPDF 2.0 no exponen esta constante, aunque existe en
# tiempo de ejecución.
ENCRYPTION_AES_256 = cast(int, pymupdf.PDF_ENCRYPT_AES_256)  # type: ignore[attr-defined]


def make_text_pdf(path: Path, *, pages: int = 1, title: str | None = None) -> Path:
    """PDF con texto nativo seleccionable."""
    document = pymupdf.open()
    for index in range(pages):
        page = document.new_page(width=A4_WIDTH, height=A4_HEIGHT)
        page.insert_text((72, 100), f"Contrato de prueba, página {index + 1}", fontsize=12)
        page.insert_text((72, 130), "Texto nativo seleccionable.", fontsize=10)
    if title is not None:
        document.set_metadata({"title": title})
    document.save(path)
    document.close()
    return path


def make_empty_pdf(path: Path) -> Path:
    """PDF con una página en blanco."""
    document = pymupdf.open()
    document.new_page(width=A4_WIDTH, height=A4_HEIGHT)
    document.save(path)
    document.close()
    return path


def make_graphic_pdf(path: Path) -> Path:
    """PDF con dibujo vectorial y sin texto ni imágenes."""
    document = pymupdf.open()
    page = document.new_page(width=A4_WIDTH, height=A4_HEIGHT)
    page.draw_rect(pymupdf.Rect(100, 100, 400, 300), color=(0.1, 0.2, 0.6), width=2)
    page.draw_line(pymupdf.Point(100, 400), pymupdf.Point(400, 400), color=(0, 0, 0), width=1)
    document.save(path)
    document.close()
    return path


def make_scanned_pdf(path: Path) -> Path:
    """PDF con una imagen que cubre toda la página, como un escaneo."""
    source = pymupdf.open()
    source_page = source.new_page(width=A4_WIDTH, height=A4_HEIGHT)
    source_page.draw_rect(source_page.rect, color=(0.8, 0.8, 0.8), fill=(0.95, 0.95, 0.95))
    source_page.insert_text((72, 100), "Texto rasterizado", fontsize=12)
    pixmap = source_page.get_pixmap(dpi=100)
    source.close()

    document = pymupdf.open()
    page = document.new_page(width=A4_WIDTH, height=A4_HEIGHT)
    page.insert_image(page.rect, pixmap=pixmap)
    document.save(path)
    document.close()
    return path


def make_encrypted_pdf(
    path: Path, *, user_password: str = "clave", owner_password: str = "propietario"
) -> Path:
    """PDF cifrado con contraseña de usuario y de propietario."""
    document = pymupdf.open()
    page = document.new_page(width=A4_WIDTH, height=A4_HEIGHT)
    page.insert_text((72, 100), "Contenido protegido", fontsize=12)
    document.save(
        path,
        encryption=ENCRYPTION_AES_256,
        owner_pw=owner_password,
        user_pw=user_password,
    )
    document.close()
    return path


def make_rotated_pdf(path: Path, *, rotation: int = 90) -> Path:
    """PDF cuya única página tiene /Rotate distinto de cero."""
    document = pymupdf.open()
    page = document.new_page(width=A4_WIDTH, height=A4_HEIGHT)
    page.insert_text((72, 100), "Página rotada", fontsize=12)
    page.set_rotation(rotation)
    document.save(path)
    document.close()
    return path


def make_rotated_empty_pdf(path: Path, *, rotation: int = 90) -> Path:
    """PDF de una página en blanco con /Rotate distinto de cero."""
    document = pymupdf.open()
    page = document.new_page(width=A4_WIDTH, height=A4_HEIGHT)
    page.set_rotation(rotation)
    document.save(path)
    document.close()
    return path


def make_cropped_rotated_pdf(
    path: Path,
    *,
    cropbox: tuple[float, float, float, float] = (50.0, 80.0, 545.0, 762.0),
    rotation: int = 90,
) -> Path:
    """PDF de una página en blanco con CropBox desplazado y /Rotate."""
    document = pymupdf.open()
    page = document.new_page(width=A4_WIDTH, height=A4_HEIGHT)
    page.set_cropbox(pymupdf.Rect(*cropbox))
    page.set_rotation(rotation)
    document.save(path)
    document.close()
    return path


def make_image_pdf(
    path: Path,
    *,
    pages: int = 1,
    color: tuple[float, float, float] = (1.0, 0.0, 0.0),
) -> Path:
    """PDF con una imagen rectangular incrustada en cada página.

    PyMuPDF reutiliza el mismo xref al insertar la misma imagen en varias
    páginas, lo que permite probar la detección de imágenes compartidas
    (RF-013).
    """
    source = pymupdf.open()
    source_page = source.new_page(width=200, height=100)
    source_page.draw_rect(source_page.rect, color=color, fill=color)
    stream = source_page.get_pixmap(alpha=False).tobytes("png")
    source.close()

    document = pymupdf.open()
    for _ in range(pages):
        page = document.new_page(width=A4_WIDTH, height=A4_HEIGHT)
        page.insert_image(pymupdf.Rect(72, 72, 272, 172), stream=stream)
    document.save(path)
    document.close()
    return path


def make_cropped_rotated_text_pdf(
    path: Path,
    *,
    cropbox: tuple[float, float, float, float] = (50.0, 80.0, 545.0, 762.0),
    rotation: int = 90,
) -> Path:
    """PDF con texto, CropBox desplazado y /Rotate."""
    document = pymupdf.open()
    page = document.new_page(width=A4_WIDTH, height=A4_HEIGHT)
    page.insert_text((72, 100), "Texto recortado", fontsize=12)
    page.set_cropbox(pymupdf.Rect(*cropbox))
    page.set_rotation(rotation)
    document.save(path)
    document.close()
    return path


def make_corrupt_file(path: Path) -> Path:
    """Archivo con contenido binario que no es un PDF."""
    path.write_bytes(bytes(range(256)) * 8)
    return path


def make_plain_text_file(path: Path) -> Path:
    """Archivo de texto que PyMuPDF podría abrir como documento no-PDF."""
    path.write_text("Esto no es un PDF, es una nota.", encoding="utf-8")
    return path
