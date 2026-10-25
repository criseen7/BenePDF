"""Verificación mínima del entorno: PyMuPDF, redacción real y Qt sin pantalla.

Se ejecuta con el Python del entorno virtual en Windows:

    .venv\\Scripts\\python.exe scripts\\verify_env.py

No forma parte de la aplicación; sirve para confirmar que las dependencias
nativas funcionan antes de escribir código de producción.
"""

from __future__ import annotations

import os
import sys
import tempfile
import traceback
from pathlib import Path

MIN_PYTHON = (3, 12)
MAX_PYTHON = (3, 13)


def check_python() -> str:
    version = sys.version_info[:2]
    if not MIN_PYTHON <= version < MAX_PYTHON:
        raise RuntimeError(
            f"Se esperaba Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}, hay {version[0]}.{version[1]}"
        )
    return f"Python {sys.version.split()[0]}"


def check_pymupdf() -> str:
    import pymupdf

    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "verificacion.pdf"

        document = pymupdf.open()
        page = document.new_page(width=200, height=100)
        page.insert_text((20, 40), "TEXTO SECRETO", fontsize=12)
        page.add_redact_annot(pymupdf.Rect(10, 20, 190, 50))
        page.apply_redactions()
        document.save(path)
        document.close()

        reopened = pymupdf.open(path)
        remaining = reopened[0].get_text().strip()
        reopened.close()

        if "SECRETO" in remaining:
            raise RuntimeError("La redacción no eliminó el texto del archivo exportado")

    return f"pymupdf {pymupdf.__version__} (redacción verificada)"


def check_qt() -> str:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PySide6.QtCore import qVersion
    from PySide6.QtGui import QColor, QImage, QPainter
    from PySide6.QtWidgets import QApplication

    application = QApplication.instance() or QApplication([])

    image = QImage(16, 16, QImage.Format.Format_RGB888)
    image.fill(QColor("white"))
    painter = QPainter(image)
    painter.fillRect(0, 0, 8, 8, QColor("black"))
    painter.end()

    if image.pixelColor(2, 2).name() != "#000000":
        raise RuntimeError("Qt no pudo dibujar en modo offscreen")

    del application
    return f"PySide6 con Qt {qVersion()} (offscreen verificado)"


def main() -> int:
    # La consola de Windows puede usar una página de códigos distinta de UTF-8.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    checks = (check_python, check_pymupdf, check_qt)
    failures = 0

    for check in checks:
        try:
            print(f"[ok] {check()}")
        except Exception:
            failures += 1
            print(f"[fallo] {check.__name__}")
            traceback.print_exc()

    if failures:
        print(f"\n{failures} comprobación(es) fallida(s)")
        return 1

    print("\nEntorno listo")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
