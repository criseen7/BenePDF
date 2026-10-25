"""Mide el tiempo de apertura y primer render para el criterio RNF-001.

Genera un PDF de texto sintético (no usa archivos personales), abre el documento
y mide cuánto tarda en estar visible la primera página:

    .venv\\Scripts\\python.exe scripts\\benchmark_open.py
    .venv\\Scripts\\python.exe scripts\\benchmark_open.py --pages 300
"""

from __future__ import annotations

import argparse
import sys
import tempfile
import time
from pathlib import Path

import pymupdf

from bene.application.use_cases.open_document import OpenDocument
from bene.application.use_cases.render_page import RenderPage
from bene.infrastructure.pdf.pymupdf_engine import PyMuPDFEngine

A4_WIDTH = 595.0
A4_HEIGHT = 842.0


def build_pdf(path: Path, pages: int) -> None:
    document = pymupdf.open()
    for index in range(pages):
        page = document.new_page(width=A4_WIDTH, height=A4_HEIGHT)
        page.insert_text((72, 100), f"Página {index + 1} de {pages}", fontsize=12)
        for line in range(25):
            page.insert_text(
                (72, 140 + line * 14),
                f"Línea de texto de relleno número {line + 1} para simular un documento.",
                fontsize=10,
            )
    document.save(path)
    document.close()


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Benchmark de apertura y primer render")
    parser.add_argument("--pages", type=int, default=100, help="páginas del PDF sintético")
    parser.add_argument("--target", type=float, default=3.0, help="objetivo en segundos (RNF-001)")
    arguments = parser.parse_args()

    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "benchmark.pdf"

        started = time.perf_counter()
        build_pdf(path, arguments.pages)
        generation = time.perf_counter() - started

        engine = PyMuPDFEngine()
        open_document = OpenDocument(engine)

        started = time.perf_counter()
        document = open_document(path)
        opened = time.perf_counter() - started

        try:
            started = time.perf_counter()
            info = document.page_info(0)
            page_info = time.perf_counter() - started

            render_page = RenderPage(document)
            started = time.perf_counter()
            render = render_page(0, scale=1.0)
            first_render = time.perf_counter() - started
        finally:
            document.close()

        total = opened + page_info + first_render
        size_mb = path.stat().st_size / (1024 * 1024)

        print(f"PDF: {arguments.pages} páginas de texto, {size_mb:.2f} MB")
        print(f"Generación del archivo:  {generation * 1000:7.1f} ms (no cuenta)")
        print(f"Apertura:                {opened * 1000:7.1f} ms")
        print(f"Info de la página 1:     {page_info * 1000:7.1f} ms")
        print(f"Render a 100 %:          {first_render * 1000:7.1f} ms")
        print(f"Clasificación pág. 1:    {info.kind.value}")
        print(f"Primera página visible:  {total:7.2f} s  (objetivo ≤ {arguments.target:.1f} s)")
        print(f"Tamaño render:           {render.width} x {render.height} px")

        if total > arguments.target:
            print("\nFallo: se supera el objetivo de RNF-001 en esta máquina.")
            return 1

    print("\nCumple el objetivo de RNF-001 en esta máquina.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
