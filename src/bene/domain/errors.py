"""Errores previstos por la aplicación.

Todos heredan de :class:`BeneError`. Los errores de documento incluyen la ruta
para que la interfaz pueda mostrar un mensaje accionable, y los de página
incluyen el índice solicitado y el total disponible.

Los mensajes están en español porque se muestran al usuario. El registro
técnico añade el tipo de excepción y la trazabilidad.
"""

from __future__ import annotations

from pathlib import Path


class BeneError(Exception):
    """Base de los errores que la aplicación sabe tratar."""


class InvalidGeometryError(BeneError, ValueError):
    """Coordenadas o dimensiones inválidas en el espacio PDF."""


class DocumentError(BeneError):
    """Error al abrir o leer un documento."""

    path: Path
    message: str

    def __init__(self, path: Path, message: str) -> None:
        super().__init__(f"{message}: {path}")
        self.path = path
        self.message = message


class DocumentNotFoundError(DocumentError):
    """La ruta indicada no existe."""

    def __init__(self, path: Path) -> None:
        super().__init__(path, "No existe el archivo")


class DocumentAccessError(DocumentError):
    """El archivo existe pero no se puede leer (permisos, bloqueo, dispositivo)."""

    def __init__(self, path: Path) -> None:
        super().__init__(path, "No se puede leer el archivo")


class UnsupportedDocumentError(DocumentError):
    """El archivo no es un PDF válido o está dañado."""

    def __init__(self, path: Path) -> None:
        super().__init__(path, "El archivo no es un PDF válido o está dañado")


class DocumentTooLargeError(DocumentError):
    """El archivo supera el límite configurado para abrirlo."""

    max_size_bytes: int

    def __init__(self, path: Path, max_size_bytes: int) -> None:
        limit_mb = max_size_bytes / (1024 * 1024)
        super().__init__(path, f"El archivo supera el límite de {limit_mb:.0f} MB")
        self.max_size_bytes = max_size_bytes


class DocumentClosedError(BeneError):
    """Se intentó usar un documento que ya se había cerrado."""

    def __init__(self) -> None:
        super().__init__("El documento ya está cerrado")


class EncryptedDocumentError(DocumentError):
    """El PDF requiere contraseña, o la facilitada no es correcta."""

    wrong_password: bool

    def __init__(self, path: Path, *, wrong_password: bool = False) -> None:
        message = (
            "La contraseña no es correcta"
            if wrong_password
            else "El documento está cifrado y requiere contraseña"
        )
        super().__init__(path, message)
        self.wrong_password = wrong_password


class PageOutOfRangeError(BeneError, IndexError):
    """El índice de página no existe en el documento."""

    page_index: int
    page_count: int

    def __init__(self, page_index: int, page_count: int) -> None:
        super().__init__(
            f"La página {page_index + 1} no existe; el documento tiene {page_count} páginas"
        )
        self.page_index = page_index
        self.page_count = page_count


class EditError(BeneError):
    """Error en una operación de edición de la sesión."""


class EditObjectNotFoundError(EditError):
    """El objeto que se quiere transformar o eliminar no existe."""

    object_id: str

    def __init__(self, object_id: str) -> None:
        super().__init__(f"No existe el objeto de edición {object_id!r}")
        self.object_id = object_id


class InvalidEditOperationError(EditError, ValueError):
    """El comando no se puede aplicar al estado actual de la edición."""


class ExportError(BeneError):
    """No se pudo materializar la edición en un archivo nuevo."""

    message: str

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class RenderError(BeneError):
    """El motor no pudo renderizar una página."""

    page_index: int
    reason: str

    def __init__(self, page_index: int, reason: str) -> None:
        super().__init__(f"No se pudo renderizar la página {page_index + 1}: {reason}")
        self.page_index = page_index
        self.reason = reason


class SearchError(BeneError):
    """La búsqueda de texto no se pudo completar."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


class ImageDetectionError(BeneError):
    """No se pudieron identificar las imágenes incrustadas de una página."""

    page_index: int

    def __init__(self, page_index: int, reason: str) -> None:
        super().__init__(
            f"No se pudieron detectar las imágenes de la página {page_index + 1}: {reason}"
        )
        self.page_index = page_index
