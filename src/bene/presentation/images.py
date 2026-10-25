"""Carga y validación de imágenes locales para insertar en el PDF (RF-011)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

from PySide6.QtGui import QImage

MAX_IMAGE_BYTES: Final[int] = 20 * 1024 * 1024

_MIME_BY_SUFFIX: Final[dict[str, str]] = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}


class ImageLoadError(ValueError):
    """La imagen no se puede leer o no tiene un formato admitido."""


@dataclass(frozen=True, slots=True)
class LoadedImage:
    """Bytes y metadatos de una imagen validada."""

    data: bytes
    mime_type: str
    source_path: Path
    width: int
    height: int


def load_image(path: Path) -> LoadedImage:
    """Lee una imagen PNG o JPEG y comprueba que Qt puede decodificarla."""
    suffix = path.suffix.lower()
    mime_type = _MIME_BY_SUFFIX.get(suffix)
    if mime_type is None:
        raise ImageLoadError("Solo se admiten imágenes PNG o JPEG")

    try:
        size = path.stat().st_size
        if size > MAX_IMAGE_BYTES:
            limit_mb = MAX_IMAGE_BYTES // (1024 * 1024)
            raise ImageLoadError(f"La imagen supera el límite de {limit_mb} MB")
        data = path.read_bytes()
    except OSError as error:
        raise ImageLoadError(f"No se puede leer la imagen: {path}") from error

    if not data:
        raise ImageLoadError("El archivo de imagen está vacío")

    image = QImage.fromData(data)
    if image.isNull() or image.width() <= 0 or image.height() <= 0:
        raise ImageLoadError("El archivo no contiene una imagen PNG o JPEG válida")

    return LoadedImage(
        data=data,
        mime_type=mime_type,
        source_path=path,
        width=image.width(),
        height=image.height(),
    )
