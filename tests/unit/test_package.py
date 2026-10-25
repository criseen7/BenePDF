"""Prueba de humo del paquete: confirma que la instalación editable funciona."""

from __future__ import annotations

import pdf_studio


def test_version_instalada() -> None:
    assert pdf_studio.__version__ == "0.1.0"
