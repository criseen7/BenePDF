"""Pruebas de carga validada de imágenes locales."""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QBuffer, QByteArray, QIODevice
from PySide6.QtGui import QColor, QImage, QImageWriter

from bene.presentation import images
from bene.presentation.images import ImageLoadError, load_image

pytestmark = pytest.mark.ui


def write_image(path: Path, fmt: bytes = b"PNG") -> Path:
    image = QImage(4, 3, QImage.Format.Format_RGB888)
    image.fill(QColor("#3366cc"))
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    writer = QImageWriter(buffer, fmt)
    assert writer.write(image)
    buffer.close()
    path.write_bytes(bytes(data.data()))
    return path


def test_carga_png(tmp_path: Path) -> None:
    path = write_image(tmp_path / "foto.png")

    loaded = load_image(path)

    assert loaded.mime_type == "image/png"
    assert (loaded.width, loaded.height) == (4, 3)
    assert loaded.source_path == path
    assert loaded.data


def test_carga_jpeg(tmp_path: Path) -> None:
    path = write_image(tmp_path / "foto.jpg", b"JPEG")

    loaded = load_image(path)

    assert loaded.mime_type == "image/jpeg"


def test_rechaza_extension_no_admitida(tmp_path: Path) -> None:
    path = write_image(tmp_path / "foto.gif")

    with pytest.raises(ImageLoadError, match="PNG o JPEG"):
        load_image(path)


def test_rechaza_contenido_invalido(tmp_path: Path) -> None:
    path = tmp_path / "falsa.png"
    path.write_bytes(b"no soy una imagen")

    with pytest.raises(ImageLoadError, match="válida"):
        load_image(path)


def test_rechaza_archivo_vacio(tmp_path: Path) -> None:
    path = tmp_path / "vacia.png"
    path.write_bytes(b"")

    with pytest.raises(ImageLoadError, match="vacío"):
        load_image(path)


def test_rechaza_archivo_demasiado_grande(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = write_image(tmp_path / "grande.png")
    monkeypatch.setattr(images, "MAX_IMAGE_BYTES", 10)

    with pytest.raises(ImageLoadError, match="límite"):
        load_image(path)


def test_rechaza_archivo_inexistente(tmp_path: Path) -> None:
    with pytest.raises(ImageLoadError, match="No se puede leer"):
        load_image(tmp_path / "no-existe.png")
