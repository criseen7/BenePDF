"""Construye un ejecutable de Bene PDF con PyInstaller (RNF-016).

Uso:

    .venv\\Scripts\\python.exe scripts\\build_app.py
    .venv\\Scripts\\python.exe scripts\\build_app.py --onefile
    .venv\\Scripts\\python.exe scripts\\build_app.py --dry-run

El resultado queda en ``dist/BenePDF`` (o en ``dist/BenePDF.exe`` con
``--onefile``). PyInstaller no forma parte de las dependencias de ejecución;
se instala con el extra ``build``.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import shlex
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Final

APP_NAME: Final[str] = "BenePDF"
ROOT: Final[Path] = Path(__file__).resolve().parents[1]
ENTRY_POINT: Final[Path] = ROOT / "src" / "bene" / "main.py"
FONTS_DIRECTORY: Final[Path] = ROOT / "src" / "bene" / "assets" / "fonts"


class BuildError(RuntimeError):
    """El entorno no está listo para construir el ejecutable."""


def build_command(*, onefile: bool = False) -> list[str]:
    """Comando de PyInstaller con el motor, las fuentes y el punto de entrada."""
    separator = ";" if os.name == "nt" else ":"
    mode = "--onefile" if onefile else "--onedir"
    return [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--name",
        APP_NAME,
        mode,
        "--add-data",
        f"{FONTS_DIRECTORY}{separator}bene/assets/fonts",
        "--collect-all",
        "pymupdf",
        str(ENTRY_POINT),
    ]


def executable_path(*, onefile: bool = False) -> Path:
    """Ruta esperada del ejecutable generado."""
    suffix = ".exe" if os.name == "nt" else ""
    if onefile:
        return ROOT / "dist" / f"{APP_NAME}{suffix}"
    return ROOT / "dist" / APP_NAME / f"{APP_NAME}{suffix}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="build_app",
        description="Construye el ejecutable de Bene PDF con PyInstaller.",
    )
    parser.add_argument(
        "--onefile",
        action="store_true",
        help="genera un único archivo ejecutable en lugar de una carpeta",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="muestra el comando de PyInstaller sin ejecutarlo",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(None if argv is None else list(argv))
    command = build_command(onefile=arguments.onefile)

    if arguments.dry_run:
        print(shlex.join(command))
        return 0

    if importlib.util.find_spec("PyInstaller") is None:
        raise BuildError(
            'PyInstaller no está instalado. Instálalo con: python -m pip install -e ".[build]"'
        )
    if not FONTS_DIRECTORY.is_dir():
        raise BuildError(f"No se encontró el directorio de fuentes: {FONTS_DIRECTORY}")

    print(f"Construyendo {APP_NAME} con PyInstaller…")
    result = subprocess.run(command, cwd=ROOT, check=False)
    if result.returncode != 0:
        print(
            f"PyInstaller falló con el código {result.returncode}.",
            file=sys.stderr,
        )
        return result.returncode

    print(f"Ejecutable creado: {executable_path(onefile=arguments.onefile)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
