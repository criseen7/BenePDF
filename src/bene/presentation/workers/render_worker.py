"""Renderizado de páginas fuera del hilo de interfaz (RNF-002, RNF-003).

El planificador mantiene como máximo un render en curso y uno pendiente: si el
usuario cambia de página o de zoom mientras se dibuja, los estados intermedios
se descartan en lugar de acumular trabajo. Solo se entrega el resultado de la
última petición.

Qt exige que los ``QObject`` vivan en el hilo de interfaz: la tarea se ejecuta
en el ``QThreadPool`` y comunica por señales, que Qt entrega en cola al hilo de
la ventana.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

from bene.application.ports.pdf_engine import RenderedPage

logger = logging.getLogger(__name__)


class PageRenderer(Protocol):
    """Caso de uso de render tal como lo consume la interfaz."""

    def __call__(self, page_index: int, *, scale: float, rotation: int = 0) -> RenderedPage: ...


@dataclass(frozen=True, slots=True)
class RenderRequest:
    page_index: int
    scale: float
    rotation: int
    token: int


class _TaskSignals(QObject):
    rendered = Signal(object, object)  # (RenderRequest, RenderedPage)
    failed = Signal(object, object)  # (RenderRequest, Exception)


class _RenderTask(QRunnable):
    def __init__(self, renderer: PageRenderer, request: RenderRequest) -> None:
        super().__init__()
        # La tarea se conserva desde el planificador hasta que llega su señal;
        # así el objeto de señales no se destruye antes de entregar el resultado.
        self.setAutoDelete(False)
        self._renderer = renderer
        self._request = request
        self.signals = _TaskSignals()

    def run(self) -> None:
        request = self._request
        try:
            result = self._renderer(
                request.page_index, scale=request.scale, rotation=request.rotation
            )
        except Exception as error:  # se informa en el hilo de interfaz
            logger.warning("Fallo al renderizar la página %d: %s", request.page_index + 1, error)
            self.signals.failed.emit(request, error)
        else:
            self.signals.rendered.emit(request, result)


class RenderScheduler(QObject):
    """Serializa y agrupa las peticiones de render de un documento."""

    rendered = Signal(object)  # RenderedPage
    failed = Signal(object)  # Exception

    def __init__(self, renderer: PageRenderer, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._renderer = renderer
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(1)
        self._pending: RenderRequest | None = None
        self._in_flight = False
        self._latest_token = 0
        self._current_task: _RenderTask | None = None

    @property
    def is_busy(self) -> bool:
        return self._in_flight or self._pending is not None

    def request(self, page_index: int, scale: float, rotation: int = 0) -> None:
        self._latest_token += 1
        self._pending = RenderRequest(
            page_index=page_index,
            scale=scale,
            rotation=rotation,
            token=self._latest_token,
        )
        self._start_next()

    def cancel_pending(self) -> None:
        """Descarta lo pendiente e invalida el resultado del render en curso."""
        self._pending = None
        self._latest_token += 1

    def shutdown(self, timeout_ms: int = 5000) -> None:
        """Espera a que termine el trabajo en curso antes de cerrar el documento."""
        self.cancel_pending()
        self._pool.clear()
        if not self._pool.waitForDone(timeout_ms):
            logger.warning("El render en curso no terminó en %d ms", timeout_ms)

    def _start_next(self) -> None:
        if self._in_flight or self._pending is None:
            return

        request = self._pending
        self._pending = None
        self._in_flight = True

        task = _RenderTask(self._renderer, request)
        task.signals.rendered.connect(self._on_rendered)
        task.signals.failed.connect(self._on_failed)
        self._current_task = task
        self._pool.start(task)

    @Slot(object, object)
    def _on_rendered(self, request: RenderRequest, result: RenderedPage) -> None:
        self._in_flight = False
        self._current_task = None
        if request.token == self._latest_token:
            self.rendered.emit(result)
        self._start_next()

    @Slot(object, object)
    def _on_failed(self, request: RenderRequest, error: Exception) -> None:
        self._in_flight = False
        self._current_task = None
        if request.token == self._latest_token:
            self.failed.emit(error)
        self._start_next()
