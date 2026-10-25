"""Pruebas de interfaz: composición de dependencias y registro."""

from __future__ import annotations

from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot

from bene.bootstrap import create_application
from bene.config import APP_NAME, AppPaths
from bene.infrastructure.logging.setup import reset_logging
from tests.integration import synthetic

pytestmark = pytest.mark.ui


def test_compone_la_aplicacion(qtbot: QtBot, tmp_path: Path) -> None:
    paths = AppPaths(data_dir=tmp_path / "datos", log_dir=tmp_path / "registros")

    app = create_application(paths=paths)
    qtbot.addWidget(app.main_window)
    try:
        assert app.paths == paths
        assert app.main_window.document_info is None
        assert app.main_window.windowTitle() == APP_NAME

        log_path = paths.log_dir / "bene.log"
        assert log_path.is_file()
        content = log_path.read_text(encoding="utf-8")
        assert f"Iniciando {APP_NAME}" in content
        assert "Registro técnico en" in content
    finally:
        app.main_window.close()
        reset_logging()


def test_el_registro_no_contiene_el_texto_del_documento(qtbot: QtBot, tmp_path: Path) -> None:
    paths = AppPaths(data_dir=tmp_path / "datos", log_dir=tmp_path / "registros")
    pdf = synthetic.make_text_pdf(tmp_path / "informe.pdf", title="Informe")

    app = create_application(paths=paths)
    qtbot.addWidget(app.main_window)
    try:
        assert app.main_window.open_path(pdf) is True
        qtbot.waitUntil(lambda: app.main_window.canvas.has_image, timeout=5000)
        app.main_window.close()

        content = (paths.log_dir / "bene.log").read_text(encoding="utf-8")
        assert "Contrato de prueba" not in content
        assert "Texto nativo seleccionable" not in content
        assert "informe.pdf" in content
    finally:
        app.main_window.close()
        reset_logging()
