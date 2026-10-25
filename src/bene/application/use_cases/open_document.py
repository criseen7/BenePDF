"""Caso de uso: abrir un documento PDF (RF-001, RF-017, RF-018)."""

from __future__ import annotations

from pathlib import Path
from typing import Final

from bene.application.ports.pdf_engine import OpenedDocument, PdfEngine
from bene.domain.errors import (
    DocumentAccessError,
    DocumentNotFoundError,
    DocumentTooLargeError,
    UnsupportedDocumentError,
)

MAX_FILE_SIZE_BYTES: Final[int] = 512 * 1024 * 1024
"""Límite por defecto para evitar abrir archivos que agoten la memoria."""


class OpenDocument:
    """Valida la ruta y delega la apertura en el motor.

    La validación de tipo de archivo no se hace por extensión: un PDF puede
    llamarse de cualquier forma y el motor comprueba el contenido real.
    """

    def __init__(
        self, engine: PdfEngine, *, max_file_size_bytes: int = MAX_FILE_SIZE_BYTES
    ) -> None:
        if max_file_size_bytes <= 0:
            raise ValueError("El tamaño máximo debe ser positivo")
        self._engine = engine
        self._max_file_size_bytes = max_file_size_bytes

    def __call__(self, path: str | Path, *, password: str | None = None) -> OpenedDocument:
        candidate = Path(path).expanduser()

        try:
            if not candidate.exists():
                raise DocumentNotFoundError(candidate)
            if not candidate.is_file():
                raise DocumentAccessError(candidate)
            size = candidate.stat().st_size
        except OSError as error:
            raise DocumentAccessError(candidate) from error

        if size == 0:
            raise UnsupportedDocumentError(candidate)
        if size > self._max_file_size_bytes:
            raise DocumentTooLargeError(candidate, self._max_file_size_bytes)

        return self._engine.open_document(candidate, password=password)
