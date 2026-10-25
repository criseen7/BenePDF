"""Caché acotada de renders, independiente de Qt (RNF-003).

Guarda las páginas ya renderizadas para que volver a una página o cambiar el
zoom no obligue a renderizar de nuevo. Se limita por número de entradas y por
memoria total; nunca se cachean todas las páginas de un documento grande.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Final

from bene.application.ports.pdf_engine import RenderedPage

RenderKey = tuple[int, float, int]
"""(página, escala redondeada, rotación de vista)."""

MAX_ENTRIES: Final[int] = 24
MAX_BYTES: Final[int] = 128 * 1024 * 1024


def _render_size(render: RenderedPage) -> int:
    return render.stride * render.height


class RenderCache:
    def __init__(
        self,
        *,
        max_entries: int = MAX_ENTRIES,
        max_bytes: int = MAX_BYTES,
    ) -> None:
        if max_entries <= 0:
            raise ValueError("El número máximo de entradas debe ser positivo")
        if max_bytes <= 0:
            raise ValueError("El tamaño máximo debe ser positivo")
        self._max_entries = max_entries
        self._max_bytes = max_bytes
        self._entries: OrderedDict[RenderKey, RenderedPage] = OrderedDict()
        self._bytes = 0

    def get(self, key: RenderKey) -> RenderedPage | None:
        render = self._entries.get(key)
        if render is None:
            return None
        self._entries.move_to_end(key)
        return render

    def put(self, key: RenderKey, render: RenderedPage) -> None:
        previous = self._entries.pop(key, None)
        if previous is not None:
            self._bytes -= _render_size(previous)

        self._entries[key] = render
        self._bytes += _render_size(render)
        self._evict()

    def clear(self) -> None:
        self._entries.clear()
        self._bytes = 0

    @property
    def size_bytes(self) -> int:
        return self._bytes

    def __len__(self) -> int:
        return len(self._entries)

    def __contains__(self, key: RenderKey) -> bool:
        return key in self._entries

    def _evict(self) -> None:
        # Se conserva al menos la entrada más reciente aunque supere el límite.
        while len(self._entries) > 1 and (
            len(self._entries) > self._max_entries or self._bytes > self._max_bytes
        ):
            _, evicted = self._entries.popitem(last=False)
            self._bytes -= _render_size(evicted)
