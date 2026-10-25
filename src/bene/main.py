"""Punto de entrada de Bene PDF."""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence

from PySide6.QtWidgets import QApplication

from bene import __version__
from bene.bootstrap import create_application
from bene.config import APP_NAME

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bene",
        description=f"{APP_NAME}: editor de PDF local.",
    )
    parser.add_argument("archivo", nargs="?", help="PDF que se abre al iniciar")
    parser.add_argument(
        "--version",
        action="version",
        version=f"{APP_NAME} {__version__}",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(None if argv is None else list(argv))

    application = QApplication(sys.argv[:1])
    application.setOrganizationName("Bene")
    application.setApplicationName(APP_NAME)
    application.setApplicationDisplayName(APP_NAME)

    try:
        app = create_application()
    except Exception:
        # Sin interfaz todavía: se registra y se sale con error.
        logger.exception("No se pudo iniciar la aplicación")
        raise

    app.main_window.show()
    if arguments.archivo:
        app.main_window.open_path(arguments.archivo)

    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
