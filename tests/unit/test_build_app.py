"""Pruebas del script de empaquetado con PyInstaller (RNF-016)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import build_app


def test_el_comando_incluye_el_motor_y_las_fuentes() -> None:
    command = build_app.build_command()

    assert command[:3] == [sys.executable, "-m", "PyInstaller"]
    assert "--noconfirm" in command
    assert "--clean" in command
    assert "--windowed" in command
    assert "--name" in command
    assert command[command.index("--name") + 1] == "BenePDF"
    assert command[command.index("--collect-all") + 1] == "pymupdf"
    assert command[-1] == str(build_app.ENTRY_POINT)

    add_data = command[command.index("--add-data") + 1]
    separator = ";" if os.name == "nt" else ":"
    source, destination = add_data.split(separator)
    assert Path(source) == build_app.FONTS_DIRECTORY
    assert destination == "bene/assets/fonts"


def test_por_defecto_genera_una_carpeta_y_admite_un_solo_archivo() -> None:
    assert "--onedir" in build_app.build_command()
    assert "--onefile" not in build_app.build_command()

    onefile = build_app.build_command(onefile=True)
    assert "--onefile" in onefile
    assert "--onedir" not in onefile


def test_la_ruta_del_ejecutable_depende_del_modo() -> None:
    suffix = ".exe" if os.name == "nt" else ""

    directory = build_app.executable_path()
    assert directory == build_app.ROOT / "dist" / "BenePDF" / f"BenePDF{suffix}"

    single = build_app.executable_path(onefile=True)
    assert single == build_app.ROOT / "dist" / f"BenePDF{suffix}"


def test_dry_run_no_invoca_pyinstaller(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fallar(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("no se debe ejecutar PyInstaller en dry-run")

    monkeypatch.setattr(build_app.subprocess, "run", fallar)

    assert build_app.main(["--dry-run"]) == 0
    output = capsys.readouterr().out
    assert "PyInstaller" in output
    assert "--windowed" in output


def test_sin_pyinstaller_el_error_indica_como_instalarlo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(build_app.importlib.util, "find_spec", lambda _name: None)

    with pytest.raises(build_app.BuildError, match="build"):
        build_app.main([])


def test_si_faltan_las_fuentes_el_error_lo_explica(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(build_app.importlib.util, "find_spec", lambda _name: object())
    monkeypatch.setattr(build_app, "FONTS_DIRECTORY", tmp_path / "no-existe")

    with pytest.raises(build_app.BuildError, match="fuentes"):
        build_app.main([])


def test_un_build_correcto_informa_de_la_ruta(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[tuple[list[str], Path]] = []

    def ejecutar(command: list[str], *, cwd: Path, check: bool) -> subprocess.CompletedProcess[str]:
        calls.append((command, cwd))
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(build_app.importlib.util, "find_spec", lambda _name: object())
    monkeypatch.setattr(build_app.subprocess, "run", ejecutar)

    assert build_app.main([]) == 0
    assert calls and calls[0][0] == build_app.build_command()
    assert calls[0][1] == build_app.ROOT
    assert str(build_app.executable_path()) in capsys.readouterr().out


def test_un_fallo_de_pyinstaller_devuelve_su_codigo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(build_app.importlib.util, "find_spec", lambda _name: object())
    monkeypatch.setattr(
        build_app.subprocess,
        "run",
        lambda command, *, cwd, check: subprocess.CompletedProcess(command, 3),
    )

    assert build_app.main([]) == 3
