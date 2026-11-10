"""Búsqueda de texto en segundo plano (RF-020, RNF-002).

El adaptador PDF serializa el acceso al documento con un cerrojo, así que se
puede buscar desde un hilo de trabajo sin bloquear la interfaz. Cada búsqueda
lleva un token: si el usuario lanza otra mientras la anterior sigue en curso, el
resultado viejo se descarta.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

from bene.application.ports.pdf_engine import OpenedDocument, SearchMatch

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SearchRequest:
    query: str
    token: int


class _SearchSignals(QObject):
    ready = Signal(object, object)  # (SearchRequest, tuple[SearchMatch, ...])
    failed = Signal(object, object)  # (SearchRequest, Exception)


class _SearchTask(QRunnable):
    def __init__(self, document: OpenedDocument, request: SearchRequest) -> None:
        super().__init__()
        self.setAutoDelete(False)
        self._document = document
        self._request = request
        self.signals = _SearchSignals()

    def run(self) -> None:
        try:
            matches = self._document.search_text(self._request.query)
        except Exception as error:
            logger.warning("Fallo al buscar %r: %s", self._request.query, error)
            self.signals.failed.emit(self._request, error)
        else:
            self.signals.ready.emit(self._request, matches)


class SearchWorker(QObject):
    """Ejecuta una búsqueda cada vez y entrega solo la última."""

    ready = Signal(str, object)  # (consulta, tuple[SearchMatch, ...])
    failed = Signal(str, object)  # (consulta, Exception)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(1)
        self._latest_token = 0
        self._current_task: _SearchTask | None = None

    @property
    def is_busy(self) -> bool:
        return self._current_task is not None

    def search(self, document: OpenedDocument, query: str) -> None:
        self._latest_token += 1
        request = SearchRequest(query=query, token=self._latest_token)
        task = _SearchTask(document, request)
        task.signals.ready.connect(self._on_ready)
        task.signals.failed.connect(self._on_failed)
        self._current_task = task
        self._pool.start(task)

    def cancel(self) -> None:
        self._latest_token += 1
        self._current_task = None

    def shutdown(self, timeout_ms: int = 5000) -> None:
        self.cancel()
        self._pool.clear()
        if not self._pool.waitForDone(timeout_ms):
            logger.warning("La búsqueda en curso no terminó en %d ms", timeout_ms)

    @Slot(object, object)
    def _on_ready(self, request: SearchRequest, matches: object) -> None:
        if not isinstance(request, SearchRequest):
            return
        if request.token != self._latest_token:
            return
        self._current_task = None
        if not isinstance(matches, Iterable):
            self.ready.emit(request.query, ())
            return
        result = tuple(match for match in matches if isinstance(match, SearchMatch))
        self.ready.emit(request.query, result)

    @Slot(object, object)
    def _on_failed(self, request: SearchRequest, error: object) -> None:
        if not isinstance(request, SearchRequest):
            return
        if request.token != self._latest_token:
            return
        self._current_task = None
        self.failed.emit(request.query, error)
