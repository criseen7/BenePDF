"""Ventana principal de Bene PDF (RF-001 a RF-005, RF-017)."""

from __future__ import annotations

import logging
import math
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Final

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QCloseEvent,
    QDragEnterEvent,
    QDropEvent,
    QKeySequence,
    QResizeEvent,
)
from PySide6.QtWidgets import (
    QDialog,
    QDockWidget,
    QFileDialog,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QScrollArea,
    QSpinBox,
    QToolBar,
    QToolButton,
    QWidget,
)

from bene.application.ports.pdf_engine import OpenedDocument, RenderedPage
from bene.application.use_cases.edit_session import EditSession
from bene.application.use_cases.export_document import ExportDocument, ExportResult
from bene.application.use_cases.open_document import OpenDocument
from bene.application.use_cases.render_page import MAX_RENDER_PIXELS
from bene.config import APP_NAME
from bene.domain.editing import EditObject, ImageObject, RedactionObject, TextObject, TextStyle
from bene.domain.errors import BeneError, EncryptedDocumentError
from bene.domain.models import DocumentInfo, PageInfo, PageKind, PdfRect
from bene.presentation.dialogs.text_dialog import TextDialog
from bene.presentation.fit import FitMode, clamp_scale, fit_scale, next_zoom, rotated_size
from bene.presentation.images import ImageLoadError, LoadedImage, load_image
from bene.presentation.render_cache import RenderCache
from bene.presentation.viewer.coordinates import CoordinateMapper
from bene.presentation.viewer.pdf_canvas import CanvasTool, PdfCanvas, rendered_page_to_image
from bene.presentation.widgets.properties_panel import ObjectPropertiesPanel
from bene.presentation.widgets.thumbnail_panel import ThumbnailPanel
from bene.presentation.workers.render_worker import PageRenderer, RenderScheduler
from bene.presentation.workers.thumbnail_worker import ThumbnailLoader, ThumbnailRequest

logger = logging.getLogger(__name__)

MAX_PASSWORD_ATTEMPTS: Final[int] = 3
RESIZE_DEBOUNCE_MS: Final[int] = 150
THUMBNAIL_SCALE: Final[float] = 0.2
DEFAULT_TEXT_WIDTH: Final[float] = 180.0
DEFAULT_TEXT_HEIGHT: Final[float] = 60.0
DEFAULT_IMAGE_WIDTH: Final[float] = 180.0

PAGE_KIND_LABELS: Final[dict[PageKind, str]] = {
    PageKind.TEXT: "texto seleccionable",
    PageKind.SCANNED: "imagen escaneada",
    PageKind.GRAPHIC: "contenido gráfico",
    PageKind.EMPTY: "página vacía",
}


class MainWindow(QMainWindow):
    def __init__(
        self,
        *,
        open_document: OpenDocument,
        renderer_factory: Callable[[OpenedDocument], PageRenderer],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._open_document = open_document
        self._renderer_factory = renderer_factory
        self._export_document = ExportDocument()

        self._document: OpenedDocument | None = None
        self._document_info: DocumentInfo | None = None
        self._scheduler: RenderScheduler | None = None
        self._page_infos: dict[int, PageInfo] = {}
        self._cache = RenderCache()
        self._edit_session: EditSession | None = None
        self._selected_object_id: str | None = None
        self._pending_text: tuple[str, TextStyle] | None = None
        self._pending_image: LoadedImage | None = None
        self._thumbnail_loader = ThumbnailLoader(self)
        self._thumbnail_loader.ready.connect(self._on_thumbnail_ready)
        self._thumbnail_loader.failed.connect(self._on_thumbnail_failed)

        self._page_index = 0
        self._zoom = 1.0
        self._view_rotation = 0
        self._fit_mode = FitMode.NONE
        self._last_directory = Path.home()

        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(RESIZE_DEBOUNCE_MS)
        self._resize_timer.timeout.connect(self._request_render)

        self._build_ui()
        self._update_ui()

    # ------------------------------------------------------------------ API

    @property
    def document_info(self) -> DocumentInfo | None:
        return self._document_info

    @property
    def page_index(self) -> int:
        return self._page_index

    @property
    def view_rotation(self) -> int:
        return self._view_rotation

    @property
    def fit_mode(self) -> FitMode:
        return self._fit_mode

    @property
    def current_scale(self) -> float:
        return self._effective_scale()

    @property
    def canvas(self) -> PdfCanvas:
        return self._canvas

    @property
    def page_description(self) -> str:
        """Texto de la barra de estado con página, tipo y dimensiones."""
        return self._status_page.text()

    @property
    def activity(self) -> str:
        """Estado del último render, visible en la barra de estado."""
        return self._status_activity.text()

    @property
    def edit_session(self) -> EditSession | None:
        return self._edit_session

    @property
    def selected_object_id(self) -> str | None:
        return self._selected_object_id

    @property
    def is_dirty(self) -> bool:
        return self._edit_session is not None and self._edit_session.is_dirty

    @property
    def edit_status(self) -> str:
        return self._status_edit.text()

    @property
    def properties_panel(self) -> ObjectPropertiesPanel:
        return self._properties

    def open_path(self, path: str | Path) -> bool:
        """Abre un documento. Devuelve ``False`` y muestra el error si falla."""
        candidate = Path(path).expanduser()
        password: str | None = None
        attempts = 0

        while True:
            try:
                document = self._open_document(candidate, password=password)
            except EncryptedDocumentError as error:
                if error.wrong_password:
                    attempts += 1
                if attempts >= MAX_PASSWORD_ATTEMPTS:
                    logger.warning("Contraseña incorrecta para %s", candidate)
                    self._show_error(error)
                    return False
                password = self._ask_password(error)
                if password is None:
                    return False
                continue
            except BeneError as error:
                logger.warning("No se pudo abrir %s: %s", candidate, error)
                self._show_error(error)
                return False
            except Exception:
                logger.exception("Error inesperado al abrir %s", candidate)
                QMessageBox.critical(
                    self,
                    APP_NAME,
                    "Se produjo un error inesperado al abrir el documento.\n"
                    "El detalle técnico está en el registro.",
                )
                return False

            if not self._confirm_discard_changes():
                document.close()
                return False

            self._install_document(document, candidate)
            return True

    def go_to_page(self, page_index: int) -> None:
        if self._document_info is None:
            return
        target = max(0, min(page_index, self._document_info.page_count - 1))
        if target == self._page_index:
            return
        self._page_index = target
        self._selected_object_id = None
        self._cancel_placement()
        self._canvas.clear_region()
        self._status_region.setText("")
        self._update_ui()
        self._request_render()

    def previous_page(self) -> None:
        self.go_to_page(self._page_index - 1)

    def next_page(self) -> None:
        self.go_to_page(self._page_index + 1)

    def set_zoom(self, scale: float) -> None:
        if self._document is None:
            return
        self._fit_mode = FitMode.NONE
        self._zoom = clamp_scale(scale)
        self._update_ui()
        self._request_render()

    def zoom_in(self) -> None:
        self.set_zoom(next_zoom(self._effective_scale(), direction=1))

    def zoom_out(self) -> None:
        self.set_zoom(next_zoom(self._effective_scale(), direction=-1))

    def set_fit_mode(self, mode: FitMode) -> None:
        if self._document is None:
            return
        self._fit_mode = mode
        self._update_ui()
        self._request_render()

    def rotate_view(self, degrees: int = 90) -> None:
        if self._document is None:
            return
        self._view_rotation = (self._view_rotation + degrees) % 360
        self._update_ui()
        self._request_render()

    def close_document(self) -> None:
        if not self._confirm_discard_changes():
            return
        self._teardown_document()
        self._update_ui()

    # ------------------------------------------------------------------- UI

    def _build_ui(self) -> None:
        self.setWindowTitle(APP_NAME)
        self.resize(1100, 850)
        self.setAcceptDrops(True)
        self.setAccessibleName(APP_NAME)
        self.setAccessibleDescription(
            "Editor de PDF local: abre, edita y exporta documentos sin conexión."
        )

        self._canvas = PdfCanvas()
        self._canvas.selection_changed.connect(self._on_selection_changed)
        self._canvas.transform_requested.connect(self._on_transform_requested)
        self._canvas.region_selected.connect(self._on_region_selected)
        self._canvas.redaction_requested.connect(self._on_redaction_requested)
        self._canvas.placement_requested.connect(self._on_placement_requested)
        self._scroll = QScrollArea(self)
        self._scroll.setWidget(self._canvas)
        self._scroll.setWidgetResizable(False)
        self._scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._scroll.setStyleSheet("QScrollArea { background: #1b1e21; border: none; }")
        self.setCentralWidget(self._scroll)

        self._thumbnails = ThumbnailPanel(self)
        self._thumbnails.setMinimumWidth(150)
        self._thumbnails.page_activated.connect(self.go_to_page)
        thumbnails_dock = QDockWidget("Páginas", self)
        thumbnails_dock.setObjectName("dock_miniaturas")
        thumbnails_dock.setWidget(self._thumbnails)
        thumbnails_dock.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
        )
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, thumbnails_dock)

        self._properties = ObjectPropertiesPanel(self)
        self._properties.geometry_applied.connect(self._on_properties_applied)
        properties_dock = QDockWidget("Propiedades", self)
        properties_dock.setObjectName("dock_propiedades")
        properties_dock.setWidget(self._properties)
        properties_dock.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
        )
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, properties_dock)

        self._open_action = QAction("Abrir…", self)
        self._open_action.setShortcut(QKeySequence.StandardKey.Open)
        self._open_action.setStatusTip("Abrir un documento PDF")
        self._open_action.triggered.connect(self._choose_file)

        self._export_action = QAction("Exportar como…", self)
        self._export_action.setObjectName("accion_exportar")
        self._export_action.setShortcut(QKeySequence("Ctrl+Shift+S"))
        self._export_action.setStatusTip(
            "Guardar una copia nueva con los cambios; el original no se modifica"
        )
        self._export_action.triggered.connect(lambda: self._export_as())

        self._zoom_in_action = QAction("Acercar", self)
        self._zoom_in_action.setShortcut(QKeySequence.StandardKey.ZoomIn)
        self._zoom_in_action.triggered.connect(self.zoom_in)

        self._zoom_out_action = QAction("Alejar", self)
        self._zoom_out_action.setShortcut(QKeySequence.StandardKey.ZoomOut)
        self._zoom_out_action.triggered.connect(self.zoom_out)

        self._zoom_reset_action = QAction("100 %", self)
        self._zoom_reset_action.setShortcut(QKeySequence("Ctrl+0"))
        self._zoom_reset_action.triggered.connect(lambda: self.set_zoom(1.0))

        self._fit_width_action = QAction("Ajustar ancho", self)
        self._fit_width_action.setShortcut(QKeySequence("Ctrl+1"))
        self._fit_width_action.triggered.connect(lambda: self.set_fit_mode(FitMode.WIDTH))

        self._fit_page_action = QAction("Ajustar página", self)
        self._fit_page_action.setShortcut(QKeySequence("Ctrl+2"))
        self._fit_page_action.triggered.connect(lambda: self.set_fit_mode(FitMode.PAGE))

        self._rotate_action = QAction("Rotar vista 90°", self)
        self._rotate_action.setShortcut(QKeySequence("Ctrl+R"))
        self._rotate_action.triggered.connect(lambda: self.rotate_view(90))

        self._close_action = QAction("Cerrar documento", self)
        self._close_action.setShortcut(QKeySequence("Ctrl+W"))
        self._close_action.triggered.connect(self.close_document)

        self._select_tool_action = QAction("Seleccionar", self)
        self._select_tool_action.setObjectName("accion_seleccionar")
        self._select_tool_action.setCheckable(True)
        self._select_tool_action.setChecked(True)
        self._select_tool_action.setShortcut(QKeySequence("Ctrl+Shift+V"))
        self._select_tool_action.triggered.connect(lambda: self.set_canvas_tool(CanvasTool.SELECT))

        self._region_tool_action = QAction("Seleccionar región", self)
        self._region_tool_action.setObjectName("accion_region")
        self._region_tool_action.setCheckable(True)
        self._region_tool_action.setShortcut(QKeySequence("Ctrl+Shift+R"))
        self._region_tool_action.triggered.connect(lambda: self.set_canvas_tool(CanvasTool.REGION))

        self._redact_tool_action = QAction("Redactar región", self)
        self._redact_tool_action.setObjectName("accion_redactar")
        self._redact_tool_action.setCheckable(True)
        self._redact_tool_action.setShortcut(QKeySequence("Ctrl+Shift+X"))
        self._redact_tool_action.setStatusTip(
            "Arrastra sobre la página para eliminar contenido de forma permanente"
        )
        self._redact_tool_action.triggered.connect(lambda: self.set_canvas_tool(CanvasTool.REDACT))

        self._tool_group = QActionGroup(self)
        self._tool_group.setExclusive(True)
        self._tool_group.addAction(self._select_tool_action)
        self._tool_group.addAction(self._region_tool_action)
        self._tool_group.addAction(self._redact_tool_action)

        self._add_text_action = QAction("Añadir texto…", self)
        self._add_text_action.setObjectName("accion_anadir_texto")
        self._add_text_action.setShortcut(QKeySequence("Ctrl+T"))
        self._add_text_action.triggered.connect(self._add_text)

        self._add_image_action = QAction("Insertar imagen…", self)
        self._add_image_action.setObjectName("accion_insertar_imagen")
        self._add_image_action.setShortcut(QKeySequence("Ctrl+I"))
        self._add_image_action.triggered.connect(self._add_image)

        self._undo_action = QAction("Deshacer", self)
        self._undo_action.setObjectName("accion_deshacer")
        self._undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        self._undo_action.triggered.connect(self.undo)

        self._redo_action = QAction("Rehacer", self)
        self._redo_action.setObjectName("accion_rehacer")
        self._redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        self._redo_action.triggered.connect(self.redo)

        self._delete_action = QAction("Eliminar objeto", self)
        self._delete_action.setObjectName("accion_eliminar_objeto")
        self._delete_action.setShortcut(QKeySequence(Qt.Key.Key_Delete))
        self._delete_action.triggered.connect(self.delete_selected_object)

        self._quit_action = QAction("Salir", self)
        self._quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        self._quit_action.triggered.connect(self.close)

        self._about_action = QAction("Acerca de Bene PDF", self)
        self._about_action.triggered.connect(self._show_about)

        self._document_actions = (
            self._zoom_in_action,
            self._zoom_out_action,
            self._zoom_reset_action,
            self._fit_width_action,
            self._fit_page_action,
            self._rotate_action,
            self._close_action,
            self._select_tool_action,
            self._region_tool_action,
            self._redact_tool_action,
            self._add_text_action,
            self._add_image_action,
            self._undo_action,
            self._redo_action,
            self._delete_action,
        )

        self._page_spin = QSpinBox(self)
        self._page_spin.setRange(1, 1)
        self._page_spin.setFixedWidth(76)
        self._page_spin.setAccessibleName("Número de página")
        self._page_spin.setAccessibleDescription(
            "Escribe un número de página o usa las flechas para cambiarla."
        )
        self._page_spin.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._page_spin.valueChanged.connect(self._on_page_spin_changed)

        self._page_total = QLabel("/ 0", self)

        self._previous_button = QToolButton(self)
        self._previous_button.setText("◀")
        self._previous_button.setAccessibleName("Página anterior")
        self._previous_button.setToolTip("Página anterior (RePág)")
        self._previous_button.setShortcut(QKeySequence("PgUp"))
        self._previous_button.clicked.connect(self.previous_page)

        self._next_button = QToolButton(self)
        self._next_button.setText("▶")
        self._next_button.setAccessibleName("Página siguiente")
        self._next_button.setToolTip("Página siguiente (AvPág)")
        self._next_button.setShortcut(QKeySequence("PgDown"))
        self._next_button.clicked.connect(self.next_page)

        toolbar = QToolBar("Principal", self)
        toolbar.setObjectName("toolbar_principal")
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        toolbar.addAction(self._open_action)
        toolbar.addAction(self._export_action)
        toolbar.addSeparator()
        toolbar.addWidget(self._previous_button)
        toolbar.addWidget(self._page_spin)
        toolbar.addWidget(self._page_total)
        toolbar.addWidget(self._next_button)
        toolbar.addSeparator()
        toolbar.addAction(self._zoom_out_action)
        toolbar.addAction(self._zoom_in_action)
        toolbar.addAction(self._fit_width_action)
        toolbar.addAction(self._fit_page_action)
        toolbar.addAction(self._zoom_reset_action)
        toolbar.addSeparator()
        toolbar.addAction(self._rotate_action)
        toolbar.addAction(self._close_action)
        toolbar.addSeparator()
        toolbar.addAction(self._select_tool_action)
        toolbar.addAction(self._region_tool_action)
        toolbar.addAction(self._redact_tool_action)
        toolbar.addAction(self._add_text_action)
        toolbar.addAction(self._add_image_action)
        toolbar.addAction(self._undo_action)
        toolbar.addAction(self._redo_action)
        toolbar.addAction(self._delete_action)
        self.addToolBar(toolbar)

        file_menu = self.menuBar().addMenu("&Archivo")
        file_menu.addAction(self._open_action)
        file_menu.addAction(self._export_action)
        file_menu.addAction(self._close_action)
        file_menu.addSeparator()
        file_menu.addAction(self._quit_action)

        edit_menu = self.menuBar().addMenu("&Edición")
        edit_menu.addAction(self._undo_action)
        edit_menu.addAction(self._redo_action)
        edit_menu.addSeparator()
        edit_menu.addAction(self._select_tool_action)
        edit_menu.addAction(self._region_tool_action)
        edit_menu.addAction(self._redact_tool_action)
        edit_menu.addSeparator()
        edit_menu.addAction(self._add_text_action)
        edit_menu.addAction(self._add_image_action)
        edit_menu.addAction(self._delete_action)

        view_menu = self.menuBar().addMenu("&Ver")
        view_menu.addAction(self._zoom_in_action)
        view_menu.addAction(self._zoom_out_action)
        view_menu.addAction(self._zoom_reset_action)
        view_menu.addSeparator()
        view_menu.addAction(self._fit_width_action)
        view_menu.addAction(self._fit_page_action)
        view_menu.addSeparator()
        view_menu.addAction(self._rotate_action)

        help_menu = self.menuBar().addMenu("A&yuda")
        help_menu.addAction(self._about_action)

        self._status_document = QLabel("Sin documento", self)
        self._status_page = QLabel("", self)
        self._status_activity = QLabel("", self)
        self._status_zoom = QLabel("100 %", self)
        self._status_region = QLabel("", self)
        self._status_edit = QLabel("Sin cambios", self)

        status = self.statusBar()
        status.addWidget(self._status_document, 1)
        status.addPermanentWidget(self._status_page)
        status.addPermanentWidget(self._status_region)
        status.addPermanentWidget(self._status_activity)
        status.addPermanentWidget(self._status_edit)
        status.addPermanentWidget(self._status_zoom)

        QWidget.setTabOrder(self._previous_button, self._page_spin)
        QWidget.setTabOrder(self._page_spin, self._next_button)
        QWidget.setTabOrder(self._next_button, self._thumbnails)
        QWidget.setTabOrder(self._thumbnails, self._canvas)

    def _update_ui(self) -> None:
        has_document = self._document_info is not None
        for action in self._document_actions:
            action.setEnabled(has_document)

        if not has_document:
            self.setWindowTitle(APP_NAME)
            self._page_spin.blockSignals(True)
            self._page_spin.setRange(1, 1)
            self._page_spin.setValue(1)
            self._page_spin.blockSignals(False)
            self._page_total.setText("/ 0")
            self._status_document.setText("Sin documento")
            self._status_page.setText("")
            self._status_activity.setText("")
            self._status_zoom.setText("100 %")
            self._canvas.set_message("Abre un PDF para empezar")
            self._thumbnails.set_page_count(0)
            self._status_region.setText("")
            self._refresh_edit_ui()
            return

        info = self._document_info
        assert info is not None

        self._export_action.setEnabled(not info.encrypted)
        if info.encrypted:
            self._export_action.setStatusTip(
                "No se puede exportar un PDF cifrado; guarda antes una copia sin protección"
            )
        else:
            self._export_action.setStatusTip(
                "Guardar una copia nueva con los cambios; el original no se modifica"
            )

        title = f"{APP_NAME} — {info.title}"
        if info.encrypted:
            title += " (cifrado)"
        self.setWindowTitle(title)
        self._status_document.setText(info.title)

        self._page_spin.blockSignals(True)
        self._page_spin.setRange(1, info.page_count)
        self._page_spin.setValue(self._page_index + 1)
        self._page_spin.blockSignals(False)
        self._page_total.setText(f"/ {info.page_count}")
        self._thumbnails.set_current_page(self._page_index)

        self._update_page_status()
        self._status_zoom.setText(f"{self._effective_scale() * 100:.0f} %")
        self._refresh_edit_ui()

    def _update_page_status(self) -> None:
        info = self._document_info
        if info is None:
            return
        try:
            page_info = self._page_info(self._page_index)
        except BeneError as error:
            logger.warning("No se pudo leer la página %d: %s", self._page_index + 1, error)
            self._status_page.setText("")
            return

        kind = PAGE_KIND_LABELS.get(page_info.kind, "tipo desconocido")
        width, height = page_info.rotated_size
        self._status_page.setText(
            f"Página {self._page_index + 1} de {info.page_count} · "
            f"{kind} · {width:.0f} × {height:.0f} pt"
        )
        self._canvas.setAccessibleDescription(self._status_page.text())

    # ------------------------------------------------------------- documento

    def _install_document(self, document: OpenedDocument, path: Path) -> None:
        self._teardown_document()

        self._document = document
        self._document_info = document.info
        self._page_infos.clear()
        self._cache.clear()
        self._page_index = 0
        self._view_rotation = 0
        self._zoom = 1.0
        self._fit_mode = FitMode.PAGE
        self._last_directory = path.parent
        self._edit_session = EditSession()
        self._selected_object_id = None
        self._pending_text = None
        self._pending_image = None
        self._canvas.clear_region()
        self._canvas.set_tool(CanvasTool.SELECT)
        self._select_tool_action.setChecked(True)

        self._scheduler = RenderScheduler(self._renderer_factory(document), self)
        self._scheduler.rendered.connect(self._on_rendered)
        self._scheduler.failed.connect(self._on_render_failed)

        logger.info("Documento abierto: %s (%d páginas)", path, document.info.page_count)
        self._thumbnails.set_page_count(document.info.page_count)
        self._update_ui()
        self._status_activity.setText("Preparando…")
        self._start_thumbnails(document)
        # El primer render espera a que el layout tenga el tamaño definitivo.
        QTimer.singleShot(0, self._request_render)

    def _start_thumbnails(self, document: OpenedDocument) -> None:
        requests = [
            ThumbnailRequest(index, THUMBNAIL_SCALE) for index in range(document.info.page_count)
        ]
        self._thumbnail_loader.start(self._renderer_factory(document), requests)

    def _on_thumbnail_ready(self, page_index: int, render: object) -> None:
        if not isinstance(render, RenderedPage):
            return
        self._thumbnails.set_thumbnail(page_index, rendered_page_to_image(render))

    def _on_thumbnail_failed(self, page_index: int, error: object) -> None:
        logger.warning("Miniatura no disponible para la página %d: %s", page_index + 1, error)

    def _teardown_document(self) -> None:
        self._thumbnail_loader.shutdown()
        if self._scheduler is not None:
            self._scheduler.shutdown()
            self._scheduler.deleteLater()
            self._scheduler = None
        if self._document is not None:
            self._document.close()
            self._document = None
        self._document_info = None
        self._page_infos.clear()
        self._cache.clear()
        self._page_index = 0
        self._view_rotation = 0
        self._zoom = 1.0
        self._fit_mode = FitMode.NONE
        self._edit_session = None
        self._selected_object_id = None
        self._pending_text = None
        self._pending_image = None
        self._canvas.set_mapper(None)
        self._canvas.set_objects(())
        self._canvas.clear_region()
        self._canvas.set_tool(CanvasTool.SELECT)
        self._canvas.set_image(None)
        self._thumbnails.set_page_count(0)
        self._properties.set_object(None)
        self._status_edit.setText("Sin cambios")
        self._status_region.setText("")

    def _page_info(self, page_index: int) -> PageInfo:
        cached = self._page_infos.get(page_index)
        if cached is not None:
            return cached
        if self._document is None:
            raise RuntimeError("No hay documento abierto")
        info = self._document.page_info(page_index)
        self._page_infos[page_index] = info
        return info

    # ---------------------------------------------------------------- render

    def _effective_scale(self) -> float:
        if self._document_info is None:
            return 1.0
        if self._fit_mode is FitMode.NONE:
            return self._zoom

        try:
            page_info = self._page_info(self._page_index)
        except BeneError:
            return self._zoom

        width, height = page_info.rotated_size
        width, height = rotated_size(width, height, self._view_rotation)
        viewport = self._scroll.viewport().size()
        available_width = viewport.width()
        # Al ajustar al ancho aparecerá la barra vertical: se descuenta su
        # espacio para que la escala no cambie y provoque un render en bucle.
        if self._fit_mode is FitMode.WIDTH:
            available_width -= self._scroll.verticalScrollBar().sizeHint().width() + 1
        return fit_scale((available_width, viewport.height()), (width, height), mode=self._fit_mode)

    def _request_render(self) -> None:
        if self._document is None or self._scheduler is None:
            return

        logical_scale = self._effective_scale()
        pixel_ratio = self._render_pixel_ratio(logical_scale)
        scale = logical_scale * pixel_ratio
        self._status_zoom.setText(f"{logical_scale * 100:.0f} %")

        key = (self._page_index, round(scale, 4), self._view_rotation)
        cached = self._cache.get(key)
        if cached is not None:
            self._show_render(cached)
            return

        self._status_activity.setText("Renderizando…")
        if not self._canvas.has_image:
            self._canvas.set_message("Renderizando página…")
        self._scheduler.request(self._page_index, scale, self._view_rotation)

    def _pixel_ratio(self) -> float:
        """Densidad de la pantalla, para renderizar con nitidez en HiDPI."""
        ratio = self._canvas.devicePixelRatioF()
        return ratio if ratio > 0 else 1.0

    def _render_pixel_ratio(self, logical_scale: float) -> float:
        """Densidad efectiva del render, recortada si no cabe en memoria.

        En pantallas HiDPI el render se pide a ``escala lógica × densidad``. En
        zooms altos eso puede superar el límite de píxeles, así que se reduce la
        densidad lo justo para no fallar; la página se sigue viendo al tamaño
        lógico correcto.
        """
        ratio = self._pixel_ratio()
        if self._document is None or logical_scale <= 0:
            return ratio
        try:
            width, height = self._page_info(self._page_index).rotated_size
        except BeneError:
            return ratio
        width, height = rotated_size(width, height, self._view_rotation)
        area = width * height
        if area <= 0:
            return ratio

        # Margen del 0,1 % para que el redondeo en coma flotante no roce el límite.
        budget_scale = math.sqrt(MAX_RENDER_PIXELS / area) * 0.999
        if logical_scale * ratio > budget_scale:
            ratio = max(1.0, budget_scale / logical_scale)
        return ratio

    def _on_rendered(self, render: object) -> None:
        if not isinstance(render, RenderedPage):
            return

        key = (render.page_index, round(render.scale, 4), render.rotation)
        self._cache.put(key, render)

        if render.page_index != self._page_index or render.rotation != self._view_rotation:
            return
        logical_scale = self._effective_scale()
        expected_scale = logical_scale * self._render_pixel_ratio(logical_scale)
        if abs(render.scale - expected_scale) > 0.01:
            # El tamaño disponible o la densidad de pantalla cambiaron mientras
            # se renderizaba (por ejemplo, al aparecer una barra de
            # desplazamiento): se pide otra vez con la escala vigente para no
            # quedarse en «Renderizando…».
            self._request_render()
            return

        self._show_render(render)

    def _on_render_failed(self, error: object) -> None:
        logger.warning("Error al renderizar: %s", error)
        self._status_activity.setText("No se pudo renderizar la página")
        if not self._canvas.has_image:
            self._canvas.set_message("No se pudo renderizar la página")
        QMessageBox.warning(self, APP_NAME, f"No se pudo renderizar la página.\n\n{error}")

    def _show_render(self, render: RenderedPage) -> None:
        logical_scale = self._effective_scale()
        pixel_ratio = render.scale / logical_scale if logical_scale > 0 else 1.0
        self._canvas.set_image(rendered_page_to_image(render, pixel_ratio=pixel_ratio))
        try:
            page_info = self._page_info(render.page_index)
        except BeneError:
            self._canvas.set_mapper(None)
        else:
            width, height = page_info.rotated_size
            self._canvas.set_mapper(
                CoordinateMapper(
                    page_width=width,
                    page_height=height,
                    scale=logical_scale,
                    view_rotation=render.rotation,
                )
            )
        self._refresh_edit_ui()
        self._status_activity.setText("Listo")
        self._update_page_status()

    # --------------------------------------------------------------- edición

    def set_canvas_tool(self, tool: CanvasTool) -> None:
        if tool is not CanvasTool.PLACE:
            self._cancel_placement()
        self._canvas.set_tool(tool)
        if tool is CanvasTool.SELECT:
            self._select_tool_action.setChecked(True)
        elif tool is CanvasTool.REGION:
            self._region_tool_action.setChecked(True)
        elif tool is CanvasTool.REDACT:
            self._redact_tool_action.setChecked(True)

    def add_text_object(
        self,
        rect: PdfRect,
        text: str,
        style: TextStyle | None = None,
    ) -> TextObject | None:
        session = self._edit_session
        if session is None or not text.strip():
            return None
        obj = session.add_text(self._page_index, rect, text, style)
        self._selected_object_id = obj.object_id
        self._refresh_edit_ui()
        return obj

    def add_image_object(
        self,
        rect: PdfRect,
        data: bytes,
        mime_type: str,
        *,
        source_path: Path | None = None,
    ) -> ImageObject | None:
        session = self._edit_session
        if session is None:
            return None
        obj = session.add_image(
            self._page_index,
            rect,
            data,
            mime_type,
            source_path=source_path,
        )
        self._selected_object_id = obj.object_id
        self._refresh_edit_ui()
        return obj

    def add_redaction_object(self, rect: PdfRect) -> RedactionObject | None:
        session = self._edit_session
        if session is None or rect.is_empty:
            return None
        obj = session.add_redaction(self._page_index, rect)
        self._selected_object_id = obj.object_id
        self._refresh_edit_ui()
        return obj

    def move_selected_object(self, rect: PdfRect) -> bool:
        session = self._edit_session
        if session is None or self._selected_object_id is None:
            return False
        session.move_object(self._selected_object_id, rect)
        self._refresh_edit_ui()
        return True

    def resize_selected_object(self, rect: PdfRect) -> bool:
        session = self._edit_session
        if session is None or self._selected_object_id is None:
            return False
        session.resize_object(self._selected_object_id, rect)
        self._refresh_edit_ui()
        return True

    def delete_selected_object(self) -> bool:
        session = self._edit_session
        if session is None or self._selected_object_id is None:
            return False
        session.delete_object(self._selected_object_id)
        self._selected_object_id = None
        self._refresh_edit_ui()
        return True

    def undo(self) -> bool:
        session = self._edit_session
        if session is None or not session.undo():
            return False
        if (
            self._selected_object_id is not None
            and session.object(self._selected_object_id) is None
        ):
            self._selected_object_id = None
        self._refresh_edit_ui()
        return True

    def redo(self) -> bool:
        session = self._edit_session
        if session is None or not session.redo():
            return False
        self._refresh_edit_ui()
        return True

    def _refresh_edit_ui(self) -> None:
        session = self._edit_session
        if session is None:
            self._canvas.set_objects(())
            self._canvas.set_overflow_ids(())
            self._properties.set_object(None)
            self._undo_action.setEnabled(False)
            self._redo_action.setEnabled(False)
            self._delete_action.setEnabled(False)
            self._status_edit.setText("Sin cambios")
            return

        if (
            self._selected_object_id is not None
            and session.object(self._selected_object_id) is None
        ):
            self._selected_object_id = None

        page_objects = session.objects_on_page(self._page_index)
        self._canvas.set_objects(page_objects)
        self._canvas.set_overflow_ids(self._overflow_ids(page_objects))
        selected = (
            session.object(self._selected_object_id)
            if self._selected_object_id is not None
            else None
        )
        self._properties.set_object(selected)
        self._undo_action.setEnabled(session.can_undo)
        self._redo_action.setEnabled(session.can_redo)
        self._delete_action.setEnabled(selected is not None)
        self._status_edit.setText("Cambios sin exportar" if session.is_dirty else "Sin cambios")
        if self._canvas.selected_object_id != self._selected_object_id:
            self._canvas.select_object(self._selected_object_id)

    def _overflow_ids(self, objects: Iterable[EditObject]) -> set[str]:
        """Textos de la página que no caben según la medición del motor."""
        document = self._document
        if document is None:
            return set()
        overflow: set[str] = set()
        for obj in objects:
            if not isinstance(obj, TextObject):
                continue
            try:
                measurement = document.measure_text(
                    obj.page_index,
                    text=obj.text,
                    rect=obj.rect,
                    font_name=obj.style.font_name,
                    font_size=obj.style.font_size,
                    alignment=obj.style.alignment,
                )
            except BeneError:
                continue
            if not measurement.fits:
                overflow.add(obj.object_id)
        return overflow

    def _on_selection_changed(self, object_id: object) -> None:
        selected = object_id if isinstance(object_id, str) else None
        self._selected_object_id = selected
        session = self._edit_session
        obj = session.object(selected) if session is not None and selected else None
        self._properties.set_object(obj)
        self._delete_action.setEnabled(obj is not None)

    def _on_transform_requested(self, object_id: str, rect: object) -> None:
        session = self._edit_session
        if session is None or not isinstance(rect, PdfRect):
            return
        current = session.object(object_id)
        if current is None:
            return
        same_size = (
            abs(current.rect.width - rect.width) < 1e-6
            and abs(current.rect.height - rect.height) < 1e-6
        )
        if same_size:
            session.move_object(object_id, rect)
        else:
            session.resize_object(object_id, rect)
        self._selected_object_id = object_id
        self._refresh_edit_ui()

    def _on_region_selected(self, region: object) -> None:
        if not isinstance(region, PdfRect):
            return
        self._status_region.setText(
            f"Región: {region.x0:.0f}, {region.y0:.0f} · "
            f"{region.width:.0f} × {region.height:.0f} pt"
        )

    def _on_redaction_requested(self, region: object) -> None:
        if not isinstance(region, PdfRect) or self._edit_session is None:
            return
        result = QMessageBox.warning(
            self,
            APP_NAME,
            "Se marcará esta región para redactarla.\n\n"
            "Al exportar, el contenido subyacente se eliminará de forma permanente "
            "del archivo nuevo y no se podrá recuperar. El PDF original no cambia.\n\n"
            "¿Marcar la región para redacción?",
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if result != QMessageBox.StandardButton.Ok:
            return
        self.add_redaction_object(region)
        self._status_activity.setText("Redacción marcada; se aplicará al exportar")

    def _on_placement_requested(self, page_x: float, page_y: float) -> None:
        if self._pending_text is not None:
            rect = self._default_text_rect(page_x, page_y)
            text, style = self._pending_text
            self._pending_text = None
            self.add_text_object(rect, text, style)
        elif self._pending_image is not None:
            loaded = self._pending_image
            self._pending_image = None
            rect = self._default_image_rect(page_x, page_y, loaded)
            self.add_image_object(
                rect,
                loaded.data,
                loaded.mime_type,
                source_path=loaded.source_path,
            )
        else:
            return

        self._canvas.clear_region()
        self.set_canvas_tool(CanvasTool.SELECT)
        self._status_activity.setText("Listo")

    def _on_properties_applied(self, x: float, y: float, width: float, height: float) -> None:
        session = self._edit_session
        if session is None or self._selected_object_id is None:
            return
        rect = self._clamped_rect(PdfRect.from_size(width, height, x=x, y=y))
        session.resize_object(self._selected_object_id, rect)
        self._refresh_edit_ui()

    def _add_text(self) -> None:
        if self._edit_session is None:
            return
        dialog = TextDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._pending_text = (dialog.text, dialog.chosen_style)
        self._pending_image = None
        region = self._canvas.region
        if region is not None:
            self._place_pending(region.x0, region.y0, region=region)
            return
        self._canvas.set_tool(CanvasTool.PLACE)
        self._status_activity.setText("Haz clic en la página para colocar el texto")

    def _add_image(self) -> None:
        if self._edit_session is None:
            return
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Insertar imagen",
            str(self._last_directory),
            "Imágenes (*.png *.jpg *.jpeg)",
        )
        if not filename:
            return
        path = Path(filename)
        try:
            loaded = load_image(path)
        except ImageLoadError as error:
            QMessageBox.warning(self, APP_NAME, str(error))
            return
        self._last_directory = path.parent
        self._pending_image = loaded
        self._pending_text = None
        region = self._canvas.region
        if region is not None:
            self._place_pending(region.x0, region.y0, region=region)
            return
        self._canvas.set_tool(CanvasTool.PLACE)
        self._status_activity.setText("Haz clic en la página para colocar la imagen")

    def _place_pending(
        self,
        page_x: float,
        page_y: float,
        *,
        region: PdfRect | None = None,
    ) -> None:
        if region is not None:
            rect = region
        elif self._pending_text is not None:
            rect = self._default_text_rect(page_x, page_y)
        elif self._pending_image is not None:
            rect = self._default_image_rect(page_x, page_y, self._pending_image)
        else:
            return

        if self._pending_text is not None:
            text, style = self._pending_text
            self._pending_text = None
            self.add_text_object(rect, text, style)
        elif self._pending_image is not None:
            loaded = self._pending_image
            self._pending_image = None
            self.add_image_object(
                rect,
                loaded.data,
                loaded.mime_type,
                source_path=loaded.source_path,
            )

        self._canvas.clear_region()
        self.set_canvas_tool(CanvasTool.SELECT)
        self._status_activity.setText("Listo")

    def _cancel_placement(self) -> None:
        self._pending_text = None
        self._pending_image = None

    def _page_size(self) -> tuple[float, float]:
        try:
            return self._page_info(self._page_index).rotated_size
        except BeneError:
            return (1.0, 1.0)

    def _default_text_rect(self, page_x: float, page_y: float) -> PdfRect:
        page_width, page_height = self._page_size()
        width = min(DEFAULT_TEXT_WIDTH, page_width)
        height = min(DEFAULT_TEXT_HEIGHT, page_height)
        return self._clamped_rect(PdfRect.from_size(width, height, x=page_x, y=page_y))

    def _default_image_rect(self, page_x: float, page_y: float, loaded: LoadedImage) -> PdfRect:
        page_width, page_height = self._page_size()
        width = min(DEFAULT_IMAGE_WIDTH, page_width)
        height = width * loaded.height / loaded.width
        if height > page_height:
            height = page_height
            width = height * loaded.width / loaded.height
        return self._clamped_rect(PdfRect.from_size(width, height, x=page_x, y=page_y))

    def _clamped_rect(self, rect: PdfRect) -> PdfRect:
        page_width, page_height = self._page_size()
        x0 = max(0.0, min(rect.x0, page_width - 1.0))
        y0 = max(0.0, min(rect.y0, page_height - 1.0))
        x1 = max(x0 + 1.0, min(rect.x1, page_width))
        y1 = max(y0 + 1.0, min(rect.y1, page_height))
        return PdfRect(x0, y0, x1, y1)

    def _confirm_discard_changes(self) -> bool:
        if not self.is_dirty:
            return True
        result = QMessageBox.warning(
            self,
            APP_NAME,
            "Hay cambios sin exportar en este documento.\n"
            "Puedes guardar una copia nueva, descartar los cambios o cancelar.",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if result == QMessageBox.StandardButton.Save:
            return self._export_as()
        return result == QMessageBox.StandardButton.Discard

    def export_document(self, destination: str | Path) -> ExportResult | None:
        """Exporta el estado actual y marca la sesión como guardada."""
        document = self._document
        session = self._edit_session
        if document is None or session is None:
            return None
        try:
            result = self._export_document(
                document,
                destination,
                objects=session.objects,
            )
        except BeneError as error:
            logger.warning("No se pudo exportar a %s: %s", destination, error)
            self._show_error(error)
            return None
        except Exception:
            logger.exception("Error inesperado al exportar a %s", destination)
            QMessageBox.critical(
                self,
                APP_NAME,
                "Se produjo un error inesperado al exportar.\n"
                "El detalle técnico está en el registro.",
            )
            return None

        session.mark_saved()
        self._last_directory = result.destination.parent
        self._refresh_edit_ui()
        self._status_activity.setText(f"Exportado: {result.destination.name}")
        logger.info(
            "Documento exportado a %s (%d redacciones, %d textos, %d imágenes)",
            result.destination,
            result.redaction_count,
            result.text_count,
            result.image_count,
        )
        return result

    def _default_export_path(self, info: DocumentInfo) -> Path:
        """Nombre de exportación que no pisa una copia anterior."""
        candidate = info.path.with_name(f"{info.path.stem}-editado.pdf")
        index = 2
        while candidate.exists():
            candidate = info.path.with_name(f"{info.path.stem}-editado-{index}.pdf")
            index += 1
        return candidate

    def _export_as(self) -> bool:
        info = self._document_info
        session = self._edit_session
        if info is None or session is None:
            return False
        if info.encrypted:
            QMessageBox.warning(
                self,
                APP_NAME,
                "No se puede exportar un PDF cifrado.\n\n"
                "Guarda antes una copia sin protección y vuelve a abrirla.",
            )
            return False

        default_path = self._default_export_path(info)
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Exportar PDF",
            str(default_path),
            "Documentos PDF (*.pdf)",
        )
        if not filename:
            return False
        destination = Path(filename)
        if destination.suffix.lower() != ".pdf":
            destination = destination.with_suffix(".pdf")

        redactions = sum(isinstance(obj, RedactionObject) for obj in session.objects)
        if redactions and not self._confirm_export_redactions(redactions):
            return False
        return self.export_document(destination) is not None

    def _confirm_export_redactions(self, count: int) -> bool:
        region_word = "región" if count == 1 else "regiones"
        result = QMessageBox.warning(
            self,
            APP_NAME,
            f"Se aplicarán {count} {region_word} de redacción al archivo exportado.\n\n"
            "El contenido subyacente se eliminará de forma permanente y no se podrá "
            "recuperar. El PDF original no se modifica.\n\n"
            "¿Exportar ahora?",
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        return result == QMessageBox.StandardButton.Ok

    # -------------------------------------------------------------- acciones

    def _choose_file(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Abrir PDF",
            str(self._last_directory),
            "Documentos PDF (*.pdf);;Todos los archivos (*)",
        )
        if filename:
            self.open_path(filename)

    def _on_page_spin_changed(self, value: int) -> None:
        self.go_to_page(value - 1)

    def _ask_password(self, error: EncryptedDocumentError) -> str | None:
        caption = "Contraseña incorrecta" if error.wrong_password else "Documento cifrado"
        password, accepted = QInputDialog.getText(
            self,
            caption,
            "Contraseña del documento:",
            QLineEdit.EchoMode.Password,
        )
        return password if accepted else None

    def _show_error(self, error: BeneError) -> None:
        QMessageBox.critical(self, APP_NAME, str(error))

    def _show_about(self) -> None:
        QMessageBox.about(
            self,
            f"Acerca de {APP_NAME}",
            f"<b>{APP_NAME}</b><br>"
            "Editor de PDF local.<br><br>"
            "Motor PDF: PyMuPDF (AGPL-3.0).<br>"
            "Interfaz: PySide6 (LGPL-3.0).",
        )

    # ------------------------------------------------------------ eventos Qt

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        if self._fit_mode is not FitMode.NONE:
            self._resize_timer.start()

    def closeEvent(self, event: QCloseEvent) -> None:
        if not self._confirm_discard_changes():
            event.ignore()
            return
        logger.info("Cerrando la aplicación")
        self._teardown_document()
        super().closeEvent(event)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if self._first_local_file(event) is not None:
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        path = self._first_local_file(event)
        if path is None:
            return
        event.acceptProposedAction()
        self.open_path(path)

    @staticmethod
    def _first_local_file(event: QDragEnterEvent | QDropEvent) -> Path | None:
        mime = event.mimeData()
        if mime is None or not mime.hasUrls():
            return None
        for url in mime.urls():
            if url.isLocalFile():
                return Path(url.toLocalFile())
        return None
