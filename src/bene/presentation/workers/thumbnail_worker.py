"""Carga secuencial de miniaturas fuera del hilo de interfaz (RNF-002)."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

from bene.application.ports.pdf_engine import RenderedPage
from bene.presentation.workers.render_worker import PageRenderer

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ThumbnailRequest:
    page_index: int
    scale: float
    rotation: int = 0


class _ThumbnailSignals(QObject):
    ready = Signal(object, object, int)  # (ThumbnailRequest, RenderedPage, generación)
    failed = Signal(object, object, int)  # (ThumbnailRequest, Exception, generación)


class _ThumbnailTask(QRunnable):
    def __init__(self, renderer: PageRenderer, request: ThumbnailRequest, generation: int) -> None:
        super().__init__()
        self.setAutoDelete(False)
        self._renderer = renderer
        self._request = request
        self._generation = generation
        self.signals = _ThumbnailSignals()

    def run(self) -> None:
        try:
            result = self._renderer(
                self._request.page_index,
                scale=self._request.scale,
                rotation=self._request.rotation,
            )
        except Exception as error:
            logger.warning(
                "No se pudo generar la miniatura de la página %d: %s",
                self._request.page_index + 1,
                error,
            )
            self.signals.failed.emit(self._request, error, self._generation)
        else:
            self.signals.ready.emit(self._request, result, self._generation)


class ThumbnailLoader(QObject):
    """Genera miniaturas de una en una y descarta lotes cancelados."""

    ready = Signal(int, object)  # (page_index, RenderedPage)
    failed = Signal(int, object)  # (page_index, Exception)
    finished = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(1)
        self._renderer: PageRenderer | None = None
        self._queue: list[ThumbnailRequest] = []
        self._current_task: _ThumbnailTask | None = None
        self._generation = 0

    @property
    def is_busy(self) -> bool:
        return self._current_task is not None or bool(self._queue)

    def start(self, renderer: PageRenderer, requests: list[ThumbnailRequest]) -> None:
        self.cancel()
        self._renderer = renderer
        self._queue = list(requests)
        if not self._queue:
            self.finished.emit()
            return
        self._start_next()

    def cancel(self) -> None:
        self._queue.clear()
        self._generation += 1
        self._current_task = None

    def shutdown(self, timeout_ms: int = 5000) -> None:
        self.cancel()
        self._pool.clear()
        if not self._pool.waitForDone(timeout_ms):
            logger.warning("La miniatura en curso no terminó en %d ms", timeout_ms)

    def _start_next(self) -> None:
        if self._current_task is not None or not self._queue or self._renderer is None:
            return

        request = self._queue.pop(0)
        task = _ThumbnailTask(self._renderer, request, self._generation)
        task.signals.ready.connect(self._on_ready)
        task.signals.failed.connect(self._on_failed)
        self._current_task = task
        self._pool.start(task)

    def _advance(self) -> None:
        self._current_task = None
        if self._queue:
            self._start_next()
        else:
            self.finished.emit()

    @Slot(object, object, int)
    def _on_ready(self, request: ThumbnailRequest, result: RenderedPage, generation: int) -> None:
        if generation != self._generation:
            return
        self.ready.emit(request.page_index, result)
        self._advance()

    @Slot(object, object, int)
    def _on_failed(self, request: ThumbnailRequest, error: Exception, generation: int) -> None:
        if generation != self._generation:
            return
        self.failed.emit(request.page_index, error)
        self._advance()
