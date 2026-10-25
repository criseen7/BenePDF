"""Configuración del registro técnico (RNF-015).

El registro va a un archivo con rotación y nunca incluye el texto del
documento. Los errores previstos se registran como advertencia; los
inesperados, con traza completa.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Final

LOG_FILENAME: Final[str] = "bene.log"
MAX_BYTES: Final[int] = 2 * 1024 * 1024
BACKUP_COUNT: Final[int] = 3

_FORMAT: Final[str] = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"

_managed_handlers: list[logging.Handler] = []


def configure_logging(log_dir: Path, *, level: int = logging.INFO) -> Path:
    """Crea el archivo de registro y conecta los manejadores.

    Es idempotente: llamarla de nuevo sustituye los manejadores que creó esta
    función, sin tocar los que añada el entorno de pruebas.
    """
    reset_logging()
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / LOG_FILENAME

    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=MAX_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(logging.Formatter(_FORMAT))

    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(file_handler)
    _managed_handlers.append(file_handler)

    # En una aplicación empaquetada para Windows puede no haber stderr.
    if sys.stderr is not None:
        console = logging.StreamHandler(sys.stderr)
        console.setLevel(logging.WARNING)
        console.setFormatter(logging.Formatter(_FORMAT))
        root.addHandler(console)
        _managed_handlers.append(console)

    return log_path


def reset_logging() -> None:
    """Desconecta y cierra los manejadores creados por esta aplicación."""
    root = logging.getLogger()
    for handler in _managed_handlers:
        root.removeHandler(handler)
        handler.close()
    _managed_handlers.clear()
