"""Rutas de datos y registros, apropiadas para cada sistema operativo (RNF-014).

Se usa la biblioteca estándar y no Qt para que el arranque, el registro y las
pruebas puedan ejecutarse sin crear una aplicación gráfica.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

APP_NAME = "Bene PDF"
APP_SLUG = "bene-pdf"


def _windows_local_app_data() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if base:
        return Path(base)
    return Path.home() / "AppData" / "Local"


def _linux_data_home() -> Path:
    base = os.environ.get("XDG_DATA_HOME")
    if base:
        return Path(base)
    return Path.home() / ".local" / "share"


def _linux_state_home() -> Path:
    base = os.environ.get("XDG_STATE_HOME")
    if base:
        return Path(base)
    return Path.home() / ".local" / "state"


def default_data_dir() -> Path:
    """Directorio de datos de la aplicación."""
    if sys.platform == "win32":
        return _windows_local_app_data() / APP_SLUG
    return _linux_data_home() / APP_SLUG


def default_log_dir() -> Path:
    """Directorio de registros. En Windows coincide con el de datos."""
    if sys.platform == "win32":
        return _windows_local_app_data() / APP_SLUG / "logs"
    return _linux_state_home() / APP_SLUG / "logs"


@dataclass(frozen=True, slots=True)
class AppPaths:
    data_dir: Path
    log_dir: Path

    @classmethod
    def default(cls) -> AppPaths:
        return cls(data_dir=default_data_dir(), log_dir=default_log_dir())
