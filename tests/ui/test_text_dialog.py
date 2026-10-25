"""Pruebas del diálogo de creación de texto."""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QDialog, QDialogButtonBox
from pytestqt.qtbot import QtBot

from bene.domain.editing import TextAlignment, TextStyle
from bene.presentation.dialogs.text_dialog import TextDialog

pytestmark = pytest.mark.ui


def ok_button(dialog: TextDialog) -> object:
    return dialog._buttons.button(QDialogButtonBox.StandardButton.Ok)


def test_valores_iniciales(qtbot: QtBot) -> None:
    dialog = TextDialog(text="Hola", style=TextStyle(font_size=18, color="#ff0000"))
    qtbot.addWidget(dialog)

    assert dialog.text == "Hola"
    assert dialog.chosen_style.font_size == 18
    assert dialog.chosen_style.color == "#ff0000"
    assert ok_button(dialog).isEnabled() is True  # type: ignore[attr-defined]


def test_desactiva_ok_sin_texto(qtbot: QtBot) -> None:
    dialog = TextDialog()
    qtbot.addWidget(dialog)

    assert ok_button(dialog).isEnabled() is False  # type: ignore[attr-defined]

    dialog._text.setPlainText("Contenido")

    assert ok_button(dialog).isEnabled() is True  # type: ignore[attr-defined]


def test_no_acepta_texto_vacio(qtbot: QtBot) -> None:
    dialog = TextDialog()
    qtbot.addWidget(dialog)

    dialog.accept()

    assert dialog.result() != QDialog.DialogCode.Accepted


def test_devuelve_el_estilo_elegido(qtbot: QtBot) -> None:
    dialog = TextDialog(text="Hola")
    qtbot.addWidget(dialog)

    dialog._font.setCurrentText("Times-Roman")
    dialog._size.setValue(24)
    dialog._alignment.setCurrentIndex(1)
    dialog.accept()

    style = dialog.chosen_style
    assert style.font_name == "Times-Roman"
    assert style.font_size == 24
    assert style.alignment is TextAlignment.CENTER
    assert dialog.result() == QDialog.DialogCode.Accepted
