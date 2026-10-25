"""Configuración común de las pruebas."""

from __future__ import annotations

import os
from collections.abc import Generator

# Las pruebas de interfaz deben poder ejecutarse en CI y desde WSL sin pantalla.
# Debe fijarse antes de importar PySide6.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication


@pytest.hookimpl(wrapper=True, tryfirst=True)
def pytest_runtest_teardown(
    item: pytest.Item, nextitem: pytest.Item | None
) -> Generator[None, object, object]:
    """Descarta los cambios pendientes antes de que pytest-qt cierre ventanas.

    Al terminar una prueba, ``qtbot`` cierra las ventanas registradas. Si la
    sesión de edición sigue con cambios, ``MainWindow`` abriría el diálogo modal
    de confirmación y el teardown se quedaría bloqueado. Vaciar la sesión antes
    equivale a descartar los cambios, que es lo que se quiere en las pruebas.

    Se registra como envoltorio ``tryfirst`` porque pytest-qt cierra las
    ventanas en su propio envoltorio de teardown, que se ejecuta antes que los
    ganchos normales.
    """
    app = QApplication.instance()
    if isinstance(app, QApplication):
        # Importación diferida: las pruebas sin interfaz no pagan el coste de Qt.
        from bene.presentation.main_window import MainWindow

        for widget in app.topLevelWidgets():
            if isinstance(widget, MainWindow) and widget.edit_session is not None:
                widget.edit_session.clear()

    return (yield)
