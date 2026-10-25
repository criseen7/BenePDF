"""Pruebas del planificador de renders en segundo plano (RNF-002)."""

from __future__ import annotations

import threading

import pytest
from pytestqt.qtbot import QtBot

from bene.application.ports.pdf_engine import RenderedPage
from bene.presentation.workers.render_worker import PageRenderer, RenderScheduler

pytestmark = pytest.mark.ui


def make_render(page_index: int, scale: float = 1.0, rotation: int = 0) -> RenderedPage:
    width = 10
    height = 10
    stride = width * 3
    return RenderedPage(
        page_index=page_index,
        width=width,
        height=height,
        stride=stride,
        samples=b"\xff" * (stride * height),
        scale=scale,
        rotation=rotation,
    )


def test_entrega_el_resultado(qtbot: QtBot) -> None:
    calls: list[tuple[int, float, int]] = []

    def renderer(page_index: int, *, scale: float, rotation: int = 0) -> RenderedPage:
        calls.append((page_index, scale, rotation))
        return make_render(page_index, scale, rotation)

    scheduler = RenderScheduler(renderer)
    try:
        with qtbot.waitSignal(scheduler.rendered, timeout=3000) as blocker:
            scheduler.request(2, 1.5, 90)

        result = blocker.args[0]
        assert isinstance(result, RenderedPage)
        assert (result.page_index, result.scale, result.rotation) == (2, 1.5, 90)
        assert calls == [(2, 1.5, 90)]
    finally:
        scheduler.shutdown()


def test_informa_del_fallo(qtbot: QtBot) -> None:
    def renderer(page_index: int, *, scale: float, rotation: int = 0) -> RenderedPage:
        raise RuntimeError("el motor falló")

    scheduler = RenderScheduler(renderer)
    try:
        with qtbot.waitSignal(scheduler.failed, timeout=3000) as blocker:
            scheduler.request(0, 1.0)

        assert isinstance(blocker.args[0], RuntimeError)
        assert str(blocker.args[0]) == "el motor falló"
    finally:
        scheduler.shutdown()


def test_agrupa_peticiones_y_descarta_las_obsoletas(qtbot: QtBot) -> None:
    gate = threading.Event()
    started = threading.Event()
    calls: list[int] = []

    def renderer(page_index: int, *, scale: float, rotation: int = 0) -> RenderedPage:
        calls.append(page_index)
        started.set()
        if not gate.wait(5):
            raise RuntimeError("la prueba no liberó el render")
        return make_render(page_index, scale, rotation)

    scheduler = RenderScheduler(renderer)
    received: list[RenderedPage] = []
    scheduler.rendered.connect(received.append)
    try:
        scheduler.request(0, 1.0)
        assert started.wait(3), "el render no llegó a empezar"

        # Mientras la página 0 se está renderizando, se piden dos más.
        scheduler.request(1, 1.0)
        scheduler.request(2, 1.0)
        assert scheduler.is_busy

        gate.set()
        qtbot.waitUntil(lambda: len(received) == 1, timeout=3000)
        qtbot.waitUntil(lambda: not scheduler.is_busy, timeout=3000)

        assert calls == [0, 2]
        assert [render.page_index for render in received] == [2]
    finally:
        gate.set()
        scheduler.shutdown()


def test_cancelar_descarta_lo_pendiente_y_lo_en_curso(qtbot: QtBot) -> None:
    gate = threading.Event()
    started = threading.Event()
    calls: list[int] = []

    def renderer(page_index: int, *, scale: float, rotation: int = 0) -> RenderedPage:
        calls.append(page_index)
        started.set()
        gate.wait(5)
        return make_render(page_index, scale, rotation)

    scheduler = RenderScheduler(renderer)
    received: list[RenderedPage] = []
    scheduler.rendered.connect(received.append)
    try:
        scheduler.request(0, 1.0)
        assert started.wait(3)
        scheduler.request(1, 1.0)

        scheduler.cancel_pending()
        gate.set()

        qtbot.waitUntil(lambda: not scheduler.is_busy, timeout=3000)
        qtbot.wait(50)

        assert calls == [0]
        assert received == []
    finally:
        gate.set()
        scheduler.shutdown()


def test_shutdown_espera_al_render_en_curso(qtbot: QtBot) -> None:
    started = threading.Event()

    def renderer(page_index: int, *, scale: float, rotation: int = 0) -> RenderedPage:
        started.set()
        return make_render(page_index, scale, rotation)

    scheduler = RenderScheduler(renderer)
    scheduler.request(0, 1.0)
    assert started.wait(3)

    scheduler.shutdown(timeout_ms=3000)
    qtbot.waitUntil(lambda: not scheduler.is_busy, timeout=3000)

    assert scheduler.is_busy is False


def test_el_renderer_cumple_el_protocolo() -> None:
    def renderer(page_index: int, *, scale: float, rotation: int = 0) -> RenderedPage:
        return make_render(page_index, scale, rotation)

    typed: PageRenderer = renderer

    assert typed(0, scale=1.0).page_index == 0
