"""Pruebas de las rutas de datos y registros (RNF-014)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import bene.config as config


@pytest.fixture
def windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "sys", SimpleNamespace(platform="win32"))


@pytest.fixture
def linux(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "sys", SimpleNamespace(platform="linux"))


@pytest.mark.usefixtures("windows")
def test_windows_usa_localappdata(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    assert config.default_data_dir() == tmp_path / "bene-pdf"
    assert config.default_log_dir() == tmp_path / "bene-pdf" / "logs"


@pytest.mark.usefixtures("windows")
def test_windows_sin_localappdata_usa_el_perfil(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))

    assert config.default_data_dir() == tmp_path / "AppData" / "Local" / "bene-pdf"
    assert config.default_log_dir() == tmp_path / "AppData" / "Local" / "bene-pdf" / "logs"


@pytest.mark.usefixtures("linux")
def test_linux_usa_xdg(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    data_home = tmp_path / "datos"
    state_home = tmp_path / "estado"
    monkeypatch.setenv("XDG_DATA_HOME", str(data_home))
    monkeypatch.setenv("XDG_STATE_HOME", str(state_home))

    assert config.default_data_dir() == data_home / "bene-pdf"
    assert config.default_log_dir() == state_home / "bene-pdf" / "logs"


@pytest.mark.usefixtures("linux")
def test_linux_sin_xdg_usa_el_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))

    assert config.default_data_dir() == tmp_path / ".local" / "share" / "bene-pdf"
    assert config.default_log_dir() == tmp_path / ".local" / "state" / "bene-pdf" / "logs"


def test_app_paths_default(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(config, "sys", SimpleNamespace(platform="linux"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "datos"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "estado"))

    paths = config.AppPaths.default()

    assert paths.data_dir == tmp_path / "datos" / "bene-pdf"
    assert paths.log_dir == tmp_path / "estado" / "bene-pdf" / "logs"


def test_app_paths_es_inmutable(tmp_path: Path) -> None:
    paths = config.AppPaths(data_dir=tmp_path, log_dir=tmp_path / "logs")

    with pytest.raises(AttributeError):
        paths.data_dir = tmp_path / "otro"  # type: ignore[misc]
