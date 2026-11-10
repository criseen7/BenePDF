"""Pruebas de los comandos de página y su deshacer/rehacer (RF-021, RF-023)."""

from __future__ import annotations

import pytest

from bene.application.use_cases.edit_session import EditSession
from bene.domain.editing import (
    AddImageReplacementCommand,
    DeletePageCommand,
    ImageReplacementObject,
    MovePageCommand,
    RotatePageCommand,
    apply_command,
    apply_page_command,
)
from bene.domain.errors import (
    EditObjectNotFoundError,
    InvalidEditOperationError,
    PageOutOfRangeError,
)
from bene.domain.models import PdfRect
from bene.domain.pages import PageArrangement


@pytest.fixture
def session() -> EditSession:
    return EditSession(page_count=3)


class TestComandosDePagina:
    def test_rotar(self) -> None:
        result = apply_page_command(PageArrangement.initial(2), RotatePageCommand(1, 90))

        assert result.rotation(1) == 90

    def test_mover(self) -> None:
        result = apply_page_command(PageArrangement.initial(3), MovePageCommand(2, 0))

        assert result.order == (2, 0, 1)

    def test_eliminar(self) -> None:
        result = apply_page_command(PageArrangement.initial(3), DeletePageCommand(1))

        assert result.order == (0, 2)

    def test_comando_desconocido(self) -> None:
        with pytest.raises(InvalidEditOperationError):
            apply_page_command(PageArrangement.initial(1), object())  # type: ignore[arg-type]


class TestReemplazoDeImagen:
    def test_anadir_reemplazo(self) -> None:
        replacement = ImageReplacementObject(
            object_id="reemplazo-1",
            page_index=0,
            image_id="5",
            rect=PdfRect(10, 10, 110, 60),
            data=b"\x89PNG",
            mime_type="image/png",
        )

        objects = apply_command({}, AddImageReplacementCommand(replacement))

        assert objects == {"reemplazo-1": replacement}

    def test_valida_identificador_y_tipo(self) -> None:
        with pytest.raises(ValueError):
            ImageReplacementObject(
                object_id="r",
                page_index=0,
                image_id=" ",
                rect=PdfRect(0, 0, 10, 10),
                data=b"x",
                mime_type="image/png",
            )
        with pytest.raises(ValueError):
            ImageReplacementObject(
                object_id="r",
                page_index=0,
                image_id="5",
                rect=PdfRect(0, 0, 10, 10),
                data=b"x",
                mime_type="image/gif",
            )

    def test_la_sesion_crea_y_deshace_el_reemplazo(self, session: EditSession) -> None:
        obj = session.replace_image(
            0,
            "5",
            PdfRect(10, 10, 110, 60),
            b"\x89PNG",
            "image/png",
        )

        assert isinstance(obj, ImageReplacementObject)
        assert obj.object_id == "reemplazo-1"
        assert session.is_dirty is True

        assert session.undo() is True
        assert not session.objects
        assert session.is_dirty is False

    def test_la_sesion_rechaza_tipo_de_imagen(self, session: EditSession) -> None:
        with pytest.raises(ValueError):
            session.replace_image(0, "5", PdfRect(0, 0, 10, 10), b"x", "image/gif")


class TestSesionDePaginas:
    def test_la_sesion_empieza_con_todas_las_paginas(self, session: EditSession) -> None:
        assert session.page_count == 3
        assert session.output_page_count == 3
        assert session.page_arrangement == PageArrangement.initial(3)

    def test_rotar_pagina(self, session: EditSession) -> None:
        session.rotate_page(1, 90)

        assert session.page_arrangement.rotation(1) == 90
        assert session.is_dirty is True

    def test_mover_pagina(self, session: EditSession) -> None:
        session.move_page(0, 2)

        assert session.page_arrangement.order == (1, 2, 0)

    def test_eliminar_pagina(self, session: EditSession) -> None:
        session.delete_page(1)

        assert list(session.page_arrangement.order) == [0, 2]
        assert session.output_page_count == 2

    def test_no_permite_eliminar_la_ultima_pagina(self) -> None:
        session = EditSession(page_count=1)

        with pytest.raises(InvalidEditOperationError):
            session.delete_page(0)

    def test_validan_los_indices(self, session: EditSession) -> None:
        with pytest.raises(PageOutOfRangeError):
            session.rotate_page(3)
        with pytest.raises(PageOutOfRangeError):
            session.move_page(0, 3)
        with pytest.raises(PageOutOfRangeError):
            session.delete_page(5)

    def test_los_objetos_validan_el_rango_de_pagina(self, session: EditSession) -> None:
        with pytest.raises(PageOutOfRangeError):
            session.add_text(3, PdfRect(10, 10, 110, 50), "Fuera")
        with pytest.raises(PageOutOfRangeError):
            session.add_image(3, PdfRect(10, 10, 110, 50), b"x", "image/png")
        with pytest.raises(PageOutOfRangeError):
            session.add_redaction(3, PdfRect(10, 10, 110, 50))
        with pytest.raises(PageOutOfRangeError):
            session.replace_image(3, "5", PdfRect(10, 10, 110, 50), b"x", "image/png")

    def test_no_permite_operar_sobre_una_pagina_eliminada(self, session: EditSession) -> None:
        session.delete_page(1)

        with pytest.raises(InvalidEditOperationError):
            session.rotate_page(1)
        with pytest.raises(InvalidEditOperationError):
            session.delete_page(1)

    def test_deshacer_y_rehacer_la_rotacion(self, session: EditSession) -> None:
        session.rotate_page(0, 90)

        assert session.undo() is True
        assert session.page_arrangement.rotation(0) == 0
        assert session.is_dirty is False

        assert session.redo() is True
        assert session.page_arrangement.rotation(0) == 90

    def test_deshacer_y_rehacer_el_movimiento(self, session: EditSession) -> None:
        session.move_page(0, 2)

        assert session.undo() is True
        assert session.page_arrangement.order == (0, 1, 2)

        assert session.redo() is True
        assert session.page_arrangement.order == (1, 2, 0)

    def test_deshacer_y_rehacer_la_eliminacion(self, session: EditSession) -> None:
        session.delete_page(1)

        assert session.undo() is True
        assert session.page_arrangement.order == (0, 1, 2)

        assert session.redo() is True
        assert list(session.page_arrangement.order) == [0, 2]

    def test_los_comandos_de_pagina_y_objeto_comparten_historial(
        self, session: EditSession
    ) -> None:
        session.add_text(0, PdfRect(10, 10, 110, 50), "Hola")
        session.rotate_page(0, 90)
        session.add_text(1, PdfRect(10, 10, 110, 50), "Mundo")

        assert session.undo() is True
        assert session.page_arrangement.rotation(0) == 90
        assert len(session.objects) == 1

        assert session.undo() is True
        assert session.page_arrangement.rotation(0) == 0
        assert len(session.objects) == 1

        assert session.undo() is True
        assert not session.objects

    def test_deshacer_una_eliminacion_conserva_los_objetos_de_la_pagina(
        self, session: EditSession
    ) -> None:
        obj = session.add_text(1, PdfRect(10, 10, 110, 50), "Hola")
        session.delete_page(1)

        # El objeto sigue en la sesión, aunque su página no se exporte.
        assert session.object(obj.object_id) == obj

        session.undo()

        assert session.object(obj.object_id) == obj
        assert session.page_arrangement.is_present(1)

    def test_no_se_puede_mover_un_objeto_de_una_pagina_eliminada(
        self, session: EditSession
    ) -> None:
        obj = session.add_text(1, PdfRect(10, 10, 110, 50), "Hola")
        session.delete_page(1)

        with pytest.raises(InvalidEditOperationError):
            session.move_object(obj.object_id, PdfRect(20, 20, 120, 60))

    def test_clear_restaura_la_disposicion_inicial(self, session: EditSession) -> None:
        session.rotate_page(0, 90)
        session.delete_page(1)

        session.clear()

        assert session.page_arrangement == PageArrangement.initial(3)
        assert session.output_page_count == 3

    def test_un_comando_de_objeto_inexistente_sigue_fallando(self, session: EditSession) -> None:
        with pytest.raises(EditObjectNotFoundError):
            session.delete_object("fantasma")
