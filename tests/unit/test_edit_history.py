"""Pruebas del historial de comandos (RF-014)."""

from __future__ import annotations

from bene.application.use_cases.edit_session import EditHistory
from bene.domain.editing import AddTextCommand, TextObject
from bene.domain.models import PdfRect


def command(object_id: str) -> AddTextCommand:
    return AddTextCommand(
        TextObject(
            object_id=object_id,
            page_index=0,
            rect=PdfRect(0, 0, 100, 40),
            text=object_id,
        )
    )


def test_empieza_vacio() -> None:
    history = EditHistory()

    assert history.commands == ()
    assert history.index == 0
    assert list(history.active_commands) == []
    assert history.can_undo is False
    assert history.can_redo is False


def test_deshacer_y_rehacer_mueven_el_indice() -> None:
    history = EditHistory()
    first = command("uno")
    second = command("dos")

    history.push(first)
    history.push(second)

    assert history.active_commands == (first, second)
    assert history.can_undo is True
    assert history.undo() == second
    assert list(history.active_commands) == [first]
    assert history.can_redo is True
    assert history.undo() == first
    assert list(history.active_commands) == []
    assert history.undo() is None
    assert history.redo() == first
    assert history.redo() == second
    assert history.redo() is None


def test_un_comando_nuevo_descarta_lo_que_habia_para_rehacer() -> None:
    history = EditHistory()
    history.push(command("uno"))
    history.push(command("dos"))
    history.undo()

    third = command("tres")
    history.push(third)

    assert history.active_commands == (command("uno"), third)
    assert history.can_redo is False
    assert history.undo() == third
    assert history.redo() == third


def test_clear() -> None:
    history = EditHistory()
    history.push(command("uno"))
    history.undo()

    history.clear()

    assert history.commands == ()
    assert history.index == 0
    assert history.can_undo is False
    assert history.can_redo is False
