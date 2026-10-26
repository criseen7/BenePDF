"""Pruebas de la sesión de edición (RF-007, RF-008, RF-011, RF-012, RF-014)."""

from __future__ import annotations

from pathlib import Path

import pytest

from bene.application.use_cases.edit_session import EditSession
from bene.domain.editing import ImageObject, RedactionObject, TextObject, TextStyle
from bene.domain.errors import EditObjectNotFoundError
from bene.domain.models import PdfRect


@pytest.fixture
def session() -> EditSession:
    return EditSession()


class TestAnadir:
    def test_anade_texto_con_estilo_y_geometria(self, session: EditSession) -> None:
        rect = PdfRect(10, 20, 210, 80)
        style = TextStyle(font_size=18, color="#ff0000")

        obj = session.add_text(0, rect, "Hola", style)

        assert isinstance(obj, TextObject)
        assert obj.object_id == "texto-1"
        assert obj.page_index == 0
        assert obj.rect == rect
        assert obj.text == "Hola"
        assert obj.style == style
        assert session.objects == (obj,)
        assert session.is_dirty is True

    def test_anade_imagen(self, session: EditSession) -> None:
        obj = session.add_image(
            1,
            PdfRect(0, 0, 100, 80),
            b"\xff\xd8\xff\xe0fake",
            "image/jpeg",
            source_path=Path("foto.jpg"),
        )

        assert isinstance(obj, ImageObject)
        assert obj.object_id == "imagen-1"
        assert obj.page_index == 1
        assert obj.mime_type == "image/jpeg"
        assert obj.source_path == Path("foto.jpg")

    def test_anade_redaccion(self, session: EditSession) -> None:
        rect = PdfRect(20, 30, 220, 90)

        obj = session.add_redaction(1, rect)

        assert isinstance(obj, RedactionObject)
        assert obj.object_id == "redaccion-1"
        assert obj.page_index == 1
        assert obj.rect == rect
        assert session.objects == (obj,)
        assert session.is_dirty is True

    def test_los_identificadores_no_se_repiten_tras_deshacer(self, session: EditSession) -> None:
        first = session.add_text(0, PdfRect(0, 0, 100, 40), "Uno")
        session.undo()

        second = session.add_text(0, PdfRect(0, 0, 100, 40), "Dos")

        assert second.object_id != first.object_id

    def test_los_objetos_se_filtran_por_pagina(self, session: EditSession) -> None:
        a = session.add_text(0, PdfRect(0, 0, 100, 40), "A")
        b = session.add_text(1, PdfRect(0, 0, 100, 40), "B")
        c = session.add_text(0, PdfRect(0, 50, 100, 90), "C")

        assert session.objects_on_page(0) == (a, c)
        assert session.objects_on_page(1) == (b,)
        assert session.objects_on_page(2) == ()

    def test_busca_por_identificador(self, session: EditSession) -> None:
        obj = session.add_text(0, PdfRect(0, 0, 100, 40), "A")

        assert session.object(obj.object_id) == obj
        assert session.object("no-existe") is None


class TestTransformar:
    def test_mueve_y_redimensiona(self, session: EditSession) -> None:
        obj = session.add_text(0, PdfRect(10, 20, 110, 60), "Hola")
        moved = PdfRect(50, 60, 150, 100)
        resized = PdfRect(50, 60, 250, 140)

        session.move_object(obj.object_id, moved)
        session.resize_object(obj.object_id, resized)

        current = session.object(obj.object_id)
        assert isinstance(current, TextObject)
        assert current.rect == resized
        assert session.can_undo is True

    def test_no_permite_transformar_un_objeto_inexistente(self, session: EditSession) -> None:
        with pytest.raises(EditObjectNotFoundError):
            session.move_object("fantasma", PdfRect(0, 0, 10, 10))

    def test_elimina(self, session: EditSession) -> None:
        obj = session.add_image(0, PdfRect(0, 0, 10, 10), b"png", "image/png")

        session.delete_object(obj.object_id)

        assert session.objects == ()
        assert session.object(obj.object_id) is None

    def test_no_permite_eliminar_un_objeto_inexistente(self, session: EditSession) -> None:
        with pytest.raises(EditObjectNotFoundError):
            session.delete_object("fantasma")


class TestHistorial:
    def test_deshacer_y_rehacer_reconstruye_el_estado(self, session: EditSession) -> None:
        obj = session.add_text(0, PdfRect(10, 20, 110, 60), "Hola")
        session.move_object(obj.object_id, PdfRect(50, 60, 150, 100))

        assert session.undo() is True
        current = session.object(obj.object_id)
        assert isinstance(current, TextObject)
        assert current.rect == PdfRect(10, 20, 110, 60)

        assert session.undo() is True
        assert session.objects == ()
        assert session.is_dirty is False
        assert session.undo() is False

        assert session.redo() is True
        assert session.object(obj.object_id) == obj
        assert session.redo() is True
        current = session.object(obj.object_id)
        assert isinstance(current, TextObject)
        assert current.rect == PdfRect(50, 60, 150, 100)
        assert session.redo() is False

    def test_una_accion_nueva_descarta_el_futuro(self, session: EditSession) -> None:
        first = session.add_text(0, PdfRect(0, 0, 100, 40), "Uno")
        session.undo()

        second = session.add_text(0, PdfRect(0, 0, 100, 40), "Dos")

        assert session.can_redo is False
        assert session.objects == (second,)
        assert session.object(first.object_id) is None

    def test_clear(self, session: EditSession) -> None:
        session.add_text(0, PdfRect(0, 0, 100, 40), "Uno")

        session.clear()

        assert session.objects == ()
        assert session.can_undo is False
        assert session.can_redo is False
        assert session.is_dirty is False


class TestEstadoLimpio:
    def test_mark_saved_deja_la_sesion_limpia(self, session: EditSession) -> None:
        session.add_text(0, PdfRect(0, 0, 100, 40), "Uno")

        session.mark_saved()

        assert session.is_dirty is False

    def test_deshacer_hasta_el_estado_guardado_queda_limpio(self, session: EditSession) -> None:
        session.add_text(0, PdfRect(0, 0, 100, 40), "Uno")
        session.mark_saved()
        session.add_text(0, PdfRect(0, 50, 100, 90), "Dos")

        session.undo()

        assert session.is_dirty is False

    def test_deshacer_y_anadir_otro_comando_vuelve_a_estar_sucio(
        self, session: EditSession
    ) -> None:
        """Mismo número de comandos activos, contenido distinto."""
        session.add_text(0, PdfRect(0, 0, 100, 40), "Uno")
        session.mark_saved()
        session.add_text(0, PdfRect(0, 50, 100, 90), "Dos")
        session.undo()

        session.add_text(0, PdfRect(0, 50, 100, 90), "Tres")

        assert session.active_command_count == 2
        assert session.is_dirty is True

    def test_redacciones_tambien_cuentan_como_cambio(self, session: EditSession) -> None:
        session.add_redaction(0, PdfRect(10, 10, 100, 40))

        assert session.is_dirty is True
        session.mark_saved()
        assert session.is_dirty is False
