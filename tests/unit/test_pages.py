"""Pruebas de la disposición de páginas y del parser de selección (RF-021)."""

from __future__ import annotations

import pytest

from bene.domain.errors import InvalidEditOperationError, PageOutOfRangeError
from bene.domain.pages import PageArrangement, parse_page_selection


class TestPageArrangement:
    def test_disposicion_inicial_conserva_todas_las_paginas(self) -> None:
        arrangement = PageArrangement.initial(3)

        assert arrangement.page_count == 3
        assert arrangement.order == (0, 1, 2)
        assert arrangement.output_page_count == 3
        assert arrangement.rotation(0) == 0
        assert arrangement.rotations == {}

    def test_documento_sin_paginas(self) -> None:
        arrangement = PageArrangement.initial(0)

        assert arrangement.order == ()
        assert arrangement.output_page_count == 0

    def test_rechaza_orden_vacio_con_paginas(self) -> None:
        with pytest.raises(ValueError):
            PageArrangement(page_count=2, order=())

    def test_rechaza_duplicados_en_el_orden(self) -> None:
        with pytest.raises(ValueError):
            PageArrangement(page_count=2, order=(0, 0))

    def test_rechaza_indices_fuera_de_rango(self) -> None:
        with pytest.raises(PageOutOfRangeError):
            PageArrangement(page_count=2, order=(0, 2))

    def test_rechaza_rotacion_no_soportada(self) -> None:
        with pytest.raises(ValueError):
            PageArrangement(page_count=2, order=(0, 1), rotations={0: 45})

    def test_las_rotaciones_no_se_pueden_mutar_desde_fuera(self) -> None:
        arrangement = PageArrangement.initial(2).rotated(0, 90)

        with pytest.raises(TypeError):
            arrangement.rotations[0] = 180  # type: ignore[index]

        assert arrangement.rotation(0) == 90

    def test_la_igualdad_incluye_las_rotaciones(self) -> None:
        base = PageArrangement.initial(2)
        rotated = base.rotated(0, 90)

        assert rotated != base
        assert rotated == PageArrangement(2, (0, 1), {0: 90})

    def test_mapea_entre_posicion_de_salida_e_indice_fuente(self) -> None:
        arrangement = PageArrangement(page_count=3, order=(2, 0))

        assert arrangement.source_index(0) == 2
        assert arrangement.source_index(1) == 0
        assert arrangement.output_index(0) == 1
        assert arrangement.output_index(1) is None
        assert arrangement.is_present(0) is True
        assert arrangement.is_present(1) is False

    def test_source_index_valida_el_rango(self) -> None:
        arrangement = PageArrangement.initial(2)

        with pytest.raises(PageOutOfRangeError):
            arrangement.source_index(2)

    def test_rotar_acumula_y_normaliza(self) -> None:
        arrangement = PageArrangement.initial(2)

        arrangement = arrangement.rotated(0, 90)
        arrangement = arrangement.rotated(0, 270)

        assert arrangement.rotation(0) == 0
        assert arrangement.rotations == {}

    def test_rotar_una_pagina_eliminada_falla(self) -> None:
        arrangement = PageArrangement(page_count=2, order=(1,))

        with pytest.raises(InvalidEditOperationError):
            arrangement.rotated(0, 90)

    def test_mover_cambia_el_orden_de_salida(self) -> None:
        arrangement = PageArrangement.initial(4)

        moved = arrangement.moved(0, 2)

        assert moved.order == (1, 2, 0, 3)
        assert moved.rotation(0) == 0

    def test_mover_valida_las_posiciones(self) -> None:
        arrangement = PageArrangement.initial(2)

        with pytest.raises(PageOutOfRangeError):
            arrangement.moved(0, 2)

    def test_eliminar_quita_la_pagina_y_su_rotacion(self) -> None:
        arrangement = PageArrangement.initial(3).rotated(1, 90)

        result = arrangement.without(1)

        assert result.order == (0, 2)
        assert result.rotations == {}

    def test_no_permite_eliminar_la_ultima_pagina(self) -> None:
        arrangement = PageArrangement(page_count=2, order=(1,))

        with pytest.raises(InvalidEditOperationError):
            arrangement.without(1)

    def test_subset_conserva_el_orden_y_las_rotaciones(self) -> None:
        arrangement = PageArrangement.initial(4).rotated(2, 90).rotated(3, 180)

        subset = arrangement.subset([3, 1])

        assert subset.page_count == 4
        assert subset.order == (3, 1)
        assert subset.rotation(3) == 180
        assert subset.rotation(1) == 0
        assert subset.rotation(2) == 0

    def test_subset_rechaza_vacio_duplicados_y_eliminadas(self) -> None:
        arrangement = PageArrangement(page_count=3, order=(0, 2))

        with pytest.raises(InvalidEditOperationError):
            arrangement.subset([])
        with pytest.raises(InvalidEditOperationError):
            arrangement.subset([0, 0])
        with pytest.raises(InvalidEditOperationError):
            arrangement.subset([1])

    def test_la_disposicion_es_inmutable(self) -> None:
        arrangement = PageArrangement.initial(2)

        arrangement.rotated(0, 90)

        assert arrangement.order == (0, 1)
        assert arrangement.rotations == {}


class TestParsePageSelection:
    def test_acepta_paginas_y_rangos(self) -> None:
        assert parse_page_selection("1-3, 5", 6) == (0, 1, 2, 4)

    def test_ordena_y_elimina_duplicados(self) -> None:
        assert parse_page_selection("5, 1-2, 2", 5) == (0, 1, 4)

    def test_admite_espacios_alrededor(self) -> None:
        assert parse_page_selection(" 1 - 2 , 4 ", 4) == (0, 1, 3)

    def test_una_sola_pagina(self) -> None:
        assert parse_page_selection("3", 3) == (2,)

    @pytest.mark.parametrize(
        "text",
        ["", "   ", "0", "2-1", "4", "1-4", "1;2", "a", "1-"],
    )
    def test_rechaza_entradas_invalidas(self, text: str) -> None:
        with pytest.raises(InvalidEditOperationError):
            parse_page_selection(text, 3)

    def test_rechaza_documento_sin_paginas(self) -> None:
        with pytest.raises(InvalidEditOperationError):
            parse_page_selection("1", 0)
