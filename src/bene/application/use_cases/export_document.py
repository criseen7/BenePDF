"""Caso de uso: exportar una copia con las ediciones materializadas (RF-009, RF-010).

El archivo original nunca se sobrescribe: el caso de uso rechaza un destino
igual al documento abierto antes de delegar en el motor. El adaptador se
encarga de escribir a un temporal, validar y reemplazar de forma atómica.
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from bene.application.ports.pdf_engine import OpenedDocument
from bene.domain.editing import EditObject, ImageObject, RedactionObject, TextObject
from bene.domain.errors import ExportError


@dataclass(frozen=True, slots=True)
class ExportResult:
    """Resumen de la exportación para mostrarlo en la interfaz."""

    destination: Path
    page_count: int
    redaction_count: int
    text_count: int
    image_count: int

    @property
    def total_objects(self) -> int:
        return self.redaction_count + self.text_count + self.image_count


class ExportDocument:
    """Valida el destino y materializa los objetos de la sesión."""

    def __call__(
        self,
        document: OpenedDocument,
        destination: str | Path,
        *,
        objects: Iterable[EditObject],
    ) -> ExportResult:
        target = Path(destination).expanduser().absolute()
        self._validate_destination(document, target)
        items = tuple(objects)
        document.export_to(target, objects=items)
        return ExportResult(
            destination=target,
            page_count=document.info.page_count,
            redaction_count=sum(isinstance(obj, RedactionObject) for obj in items),
            text_count=sum(isinstance(obj, TextObject) for obj in items),
            image_count=sum(isinstance(obj, ImageObject) for obj in items),
        )

    @staticmethod
    def _validate_destination(document: OpenedDocument, target: Path) -> None:
        source = document.info.path
        if _normalized_path(target) == _normalized_path(source):
            raise ExportError(
                "El archivo de destino debe ser distinto del PDF original; "
                "el original nunca se modifica"
            )
        if target.exists() and target.is_dir():
            raise ExportError("El destino es una carpeta; indica un nombre de archivo PDF")
        if not target.parent.is_dir():
            raise ExportError(f"No existe la carpeta de destino: {target.parent}")


def _normalized_path(path: Path) -> str:
    return os.path.normcase(str(path.expanduser().resolve()))
