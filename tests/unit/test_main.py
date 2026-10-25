"""Pruebas del punto de entrada."""

from __future__ import annotations

import pytest

from bene import __version__
from bene.config import APP_NAME
from bene.main import build_parser


def test_sin_argumentos_no_abre_ningun_archivo() -> None:
    arguments = build_parser().parse_args([])

    assert arguments.archivo is None


def test_acepta_un_archivo_posicional() -> None:
    arguments = build_parser().parse_args(["documento.pdf"])

    assert arguments.archivo == "documento.pdf"


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        build_parser().parse_args(["--version"])

    assert excinfo.value.code == 0
    output = capsys.readouterr().out
    assert APP_NAME in output
    assert __version__ in output
