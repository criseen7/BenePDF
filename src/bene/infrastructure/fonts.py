"""Fuentes abiertas embebidas y su correspondencia con los nombres lógicos.

La vista previa y la exportación deben medir el texto igual. Para conseguirlo se
empaquetan las Liberation (licencia SIL OFL), métricamente compatibles con
Helvetica, Times y Courier, y se usan en ambos lados. Los nombres lógicos del
dominio se mantienen para no atar el modelo a una fuente concreta.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from bene.domain.editing import SUPPORTED_FONTS

FONT_FILES: Final[dict[str, str]] = {
    "Helvetica": "LiberationSans-Regular.ttf",
    "Times-Roman": "LiberationSerif-Regular.ttf",
    "Courier": "LiberationMono-Regular.ttf",
}

FONT_ALIASES: Final[dict[str, str]] = {
    "Helvetica": "BeneSans",
    "Times-Roman": "BeneSerif",
    "Courier": "BeneMono",
}

FONTS_DIRECTORY: Final[Path] = Path(__file__).resolve().parents[1] / "assets" / "fonts"


def normalized_font_name(font_name: str) -> str:
    """Devuelve un nombre lógico admitido, con Helvetica como reserva."""
    return font_name if font_name in SUPPORTED_FONTS else "Helvetica"


def bundled_font_path(font_name: str) -> Path | None:
    """Ruta del TTF empaquetado, o ``None`` si falta el recurso.

    La ausencia no es un error fatal: el adaptador cae en las fuentes Base-14
    para que la aplicación siga funcionando en una instalación incompleta.
    """
    filename = FONT_FILES.get(normalized_font_name(font_name))
    if filename is None:
        return None
    path = FONTS_DIRECTORY / filename
    return path if path.is_file() else None


def font_alias(font_name: str) -> str:
    """Nombre interno con el que se registra la fuente en el PDF."""
    return FONT_ALIASES[normalized_font_name(font_name)]
