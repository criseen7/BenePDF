"""Registro en Qt de las fuentes embebidas que usa la vista previa.

El adaptador PDF usa los mismos TTF al exportar, de modo que la vista previa y
el archivo final midan el texto de forma equivalente. Si un recurso falta, se
cae en la fuente del sistema con el nombre lógico.
"""

from __future__ import annotations

from functools import cache

from PySide6.QtGui import QFontDatabase

from bene.domain.editing import SUPPORTED_FONTS
from bene.infrastructure.fonts import bundled_font_path


@cache
def qt_font_family(font_name: str) -> str:
    """Familia Qt de la fuente embebida correspondiente al nombre lógico."""
    path = bundled_font_path(font_name)
    if path is None:
        return font_name
    identifier = QFontDatabase.addApplicationFont(str(path))
    if identifier < 0:
        return font_name
    families = QFontDatabase.applicationFontFamilies(identifier)
    return families[0] if families else font_name


def register_fonts() -> None:
    """Registra todas las fuentes embebidas. Requiere una ``QApplication``."""
    for font_name in SUPPORTED_FONTS:
        qt_font_family(font_name)
