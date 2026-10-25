"""Prueba de humo del paquete: confirma que la instalación editable funciona."""

from __future__ import annotations

import bene


def test_version_instalada() -> None:
    assert bene.__version__ == "0.1.0"
