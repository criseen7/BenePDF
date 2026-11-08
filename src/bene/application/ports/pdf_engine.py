"""Puerto del motor PDF.

La interfaz no conoce PyMuPDF: solo este contrato, los modelos del dominio y
los errores tipados. Sustituir el motor implica escribir otro adaptador.

Convenciones:

- Los índices de página son **base cero**.
- Las coordenadas y dimensiones se expresan en puntos PDF (1/72 de pulgada),
  con origen en la esquina superior izquierda de la página sin rotación.
- ``scale`` es el factor de zoom: ``1.0`` renderiza a 72 ppp.
- ``rotation`` es la rotación **de vista** (0, 90, 180 o 270 grados), adicional
  a la rotación propia de la página. El resultado debe verse ya rotado.

Implementaciones: las instancias no son seguras para uso concurrente. El
adaptador debe serializar las llamadas (por ejemplo con un cerrojo) o crear una
sesión por hilo; el visor puede pedir renders desde un hilo de trabajo.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from bene.domain.editing import EditObject, TextAlignment
from bene.domain.models import DocumentInfo, PageInfo, PdfRect

BYTES_PER_PIXEL = 3
"""Los renders se entregan siempre como RGB de 8 bits por canal."""


@dataclass(frozen=True, slots=True)
class RenderedPage:
    """Imagen RGB888 de una página, lista para convertirse en mapa de bits.

    ``samples`` tiene al menos ``stride * height`` bytes; ``stride`` puede ser
    mayor que ``width * 3`` porque el motor suele alinear cada fila.
    """

    page_index: int
    width: int
    height: int
    stride: int
    samples: bytes
    scale: float
    rotation: int = 0

    def __post_init__(self) -> None:
        if self.page_index < 0:
            raise ValueError(f"Índice de página inválido: {self.page_index}")
        if self.width <= 0 or self.height <= 0:
            raise ValueError(f"Dimensiones de imagen inválidas: {self.width} x {self.height}")
        if self.stride < self.width * BYTES_PER_PIXEL:
            raise ValueError(f"Stride insuficiente: {self.stride} < {self.width * BYTES_PER_PIXEL}")
        if len(self.samples) < self.stride * self.height:
            raise ValueError(f"Faltan píxeles: {len(self.samples)} < {self.stride * self.height}")
        if not self.scale > 0:
            raise ValueError(f"Escala inválida: {self.scale}")
        if self.rotation not in (0, 90, 180, 270):
            raise ValueError(f"Rotación de vista inválida: {self.rotation}")


@dataclass(frozen=True, slots=True)
class TextMeasurement:
    """Resultado de medir un texto en su región sin modificar el documento."""

    fits: bool
    overflow_points: float = 0.0
    unsupported: tuple[str, ...] = ()


class PdfEngine(Protocol):
    """Fábrica de sesiones de documento."""

    def open_document(self, path: Path, *, password: str | None = None) -> OpenedDocument:
        """Abre un PDF y devuelve su sesión.

        Errores esperados: :class:`DocumentNotFoundError`,
        :class:`DocumentAccessError`, :class:`UnsupportedDocumentError` y
        :class:`EncryptedDocumentError`. La contraseña nunca debe registrarse.
        """
        ...


@runtime_checkable
class OpenedDocument(Protocol):
    """Documento abierto en el motor. El llamador es responsable de ``close()``."""

    @property
    def info(self) -> DocumentInfo:
        """Datos del documento, disponibles tras abrirlo."""
        ...

    def page_info(self, page_index: int) -> PageInfo:
        """Dimensiones, rotación y clasificación orientativa de la página.

        Errores esperados: :class:`PageOutOfRangeError`.
        """
        ...

    def render_page(self, page_index: int, *, scale: float, rotation: int = 0) -> RenderedPage:
        """Renderiza la página a la escala y rotación de vista indicadas.

        Errores esperados: :class:`PageOutOfRangeError` y :class:`RenderError`.
        """
        ...

    def export_to(self, destination: Path, *, objects: Iterable[EditObject]) -> None:
        """Escribe una copia nueva con las ediciones materializadas.

        La implementación no modifica el archivo original. Debe escribir a un
        archivo temporal, validar el resultado y reemplazar ``destination`` de
        forma atómica (RNF-005). Las redacciones se aplican antes que los
        textos e imágenes nuevos.

        Errores esperados: :class:`ExportError` y :class:`DocumentClosedError`.
        """
        ...

    def measure_text(
        self,
        page_index: int,
        *,
        text: str,
        rect: PdfRect,
        font_name: str,
        font_size: float,
        alignment: TextAlignment = TextAlignment.LEFT,
    ) -> TextMeasurement:
        """Comprueba si un texto cabe en su región, sin modificar la página.

        Es la medición autoritativa que comparte la exportación: la vista previa
        puede usarla para señalar un desbordamiento antes de guardar. Los
        caracteres sin glifo se devuelven en :attr:`TextMeasurement.unsupported`.

        Errores esperados: :class:`PageOutOfRangeError` y
        :class:`DocumentClosedError`.
        """
        ...

    def close(self) -> None:
        """Libera los recursos del documento. Debe poder llamarse dos veces."""
        ...
