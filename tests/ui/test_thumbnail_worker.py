"""Pruebas de la carga asíncrona de miniaturas."""

from __future__ import annotations

import time

import pytest
from pytestqt.qtbot import QtBot

from bene.application.ports.pdf_engine import RenderedPage
from bene.presentation.workers.thumbnail_worker import ThumbnailLoader, ThumbnailRequest

pytestmark = pytest.mark.ui

TIMEOUT_MS = 5000


def make_render(page_index: int, width: int = 10, height: int = 14) -> RenderedPage:
    stride = width * 3
    return RenderedPage(
        page_index=page_index,
        width=width,
        height=height,
        stride=stride,
        samples=b"\xff" * (stride * height),
        scale=0.2,
    )


def requests(count: int) -> list[ThumbnailRequest]:
    return [ThumbnailRequest(index, 0.2) for index in range(count)]


class TestCarga:
    def test_genera_las_miniaturas_en_orden(self, qtbot: QtBot) -> None:
        loader = ThumbnailLoader()
        ready: list[int] = []
        finished: list[bool] = []
        loader.ready.connect(lambda index, _render: ready.append(index))
        loader.finished.connect(lambda: finished.append(True))

        def renderer(page_index: int, *, scale: float, rotation: int = 0) -> RenderedPage:
            return make_render(page_index)

        loader.start(renderer, requests(3))

        qtbot.waitUntil(lambda: finished == [True], timeout=TIMEOUT_MS)
        assert ready == [0, 1, 2]
        assert loader.is_busy is False

    def test_un_fallo_no_detiene_el_resto(self, qtbot: QtBot) -> None:
        loader = ThumbnailLoader()
        ready: list[int] = []
        failed: list[int] = []
        finished: list[bool] = []
        loader.ready.connect(lambda index, _render: ready.append(index))
        loader.failed.connect(lambda index, _error: failed.append(index))
        loader.finished.connect(lambda: finished.append(True))

        def renderer(page_index: int, *, scale: float, rotation: int = 0) -> RenderedPage:
            if page_index == 1:
                raise RuntimeError("página rota")
            return make_render(page_index)

        loader.start(renderer, requests(3))

        qtbot.waitUntil(lambda: finished == [True], timeout=TIMEOUT_MS)
        assert ready == [0, 2]
        assert failed == [1]

    def test_start_vacio_termina(self, qtbot: QtBot) -> None:
        loader = ThumbnailLoader()
        finished: list[bool] = []
        loader.finished.connect(lambda: finished.append(True))

        loader.start(lambda *_args, **_kwargs: make_render(0), [])

        assert finished == [True]

    def test_cancelar_descarta_las_pendientes(self, qtbot: QtBot) -> None:
        loader = ThumbnailLoader()
        ready: list[int] = []
        loader.ready.connect(lambda index, _render: ready.append(index))

        def renderer(page_index: int, *, scale: float, rotation: int = 0) -> RenderedPage:
            time.sleep(0.03)
            return make_render(page_index)

        loader.start(renderer, requests(5))
        loader.cancel()

        qtbot.waitUntil(lambda: not loader.is_busy, timeout=TIMEOUT_MS)
        assert ready == []
