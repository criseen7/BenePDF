"""Configuración común de las pruebas."""

from __future__ import annotations

import os

# Las pruebas de interfaz deben poder ejecutarse en CI y desde WSL sin pantalla.
# Debe fijarse antes de importar PySide6.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
