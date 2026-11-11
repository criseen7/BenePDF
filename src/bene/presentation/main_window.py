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
    QColor,
    QDragEnterEvent,
    QDropEvent,
    QKeySequence,
    QResizeEvent,
)
from PySide6.QtWidgets import (
    QColorDialog,
    QDialog,
    QDockWidget,
    QDoubleSpinBox,
    QFileDialog,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QToolBar,
    QToolButton,
    QWidget,
)

from bene.application.ports.pdf_engine import OpenedDocument, RenderedPage, SearchMatch
from bene.application.use_cases.edit_session import EditSession
from bene.application.use_cases.export_document import ExportDocument, ExportResult
from bene.application.use_cases.open_document import OpenDocument
from bene.application.use_cases.render_page import MAX_RENDER_PIXELS
from bene.config import APP_NAME
from bene.domain.editing import (
    EditObject,
    ImageObject,
    ImageReplacementObject,
    RedactionObject,
    StrokeObject,
    StrokeStyle,
    TextObject,
    TextStyle,
)
from bene.domain.errors import BeneError, EncryptedDocumentError
from bene.domain.models import DocumentInfo, PageInfo, PageKind, PdfRect
from bene.domain.pages import PageArrangement, parse_page_selection
from bene.presentation.dialogs.document_info_dialog import DocumentInfoDialog
from bene.presentation.dialogs.image_replacement_dialog import ImageReplacementDialog
from bene.presentation.dialogs.text_dialog import TextDialog
from bene.presentation.fit import FitMode, clamp_scale, fit_scale, next_zoom, rotated_size
from bene.presentation.images import ImageLoadError, LoadedImage, load_image
from bene.presentation.render_cache import RenderCache
from bene.presentation.viewer.coordinates import CoordinateMapper
from bene.presentation.viewer.pdf_canvas import CanvasTool, PdfCanvas, rendered_page_to_image
from bene.presentation.widgets.properties_panel import ObjectPropertiesPanel
from bene.presentation.widgets.search_panel import SearchPanel
from bene.presentation.widgets.thumbnail_panel import ThumbnailPanel
from bene.presentation.workers.render_worker import PageRenderer, RenderScheduler
from bene.presentation.workers.search_worker import SearchWorker
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
        self._last_text_style: TextStyle | None = None
        self._stroke_style = StrokeStyle()
        self._stroke_color = QColor(self._stroke_style.color)
        self._thumbnail_loader = ThumbnailLoader(self)
        self._thumbnail_loader.ready.connect(self._on_thumbnail_ready)
        self._thumbnail_loader.failed.connect(self._on_thumbnail_failed)
        self._search_worker = SearchWorker(self)
        self._search_worker.ready.connect(self._on_search_ready)
        self._search_worker.failed.connect(self._on_search_failed)
        self._search_matches: tuple[SearchMatch, ...] = ()
        self._current_search_match: SearchMatch | None = None

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

    @property
    def stroke_style(self) -> StrokeStyle:
        """Color y grosor con los que se crearán los trazos nuevos."""
        return self._stroke_style

    @property
    def stroke_width_spin(self) -> QDoubleSpinBox:
        return self._stroke_width

    @property
    def stroke_color_button(self) -> QPushButton:
        return self._stroke_color_button

    @property
    def draw_action(self) -> QAction:
        return self._draw_tool_action

    @property
    def search_panel(self) -> SearchPanel:
        return self._search

    @property
    def search_matches(self) -> tuple[SearchMatch, ...]:
        return self._search_matches

    @property
    def current_search_match(self) -> SearchMatch | None:
        return self._current_search_match

    @property
    def output_page_count(self) -> int:
        session = self._edit_session
        if session is not None:
            return session.output_page_count
        return self._document_info.page_count if self._document_info is not None else 0

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
        page_count = self.output_page_count
        target = max(0, min(page_index, page_count - 1))
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
        self._canvas.stroke_requested.connect(self._on_stroke_requested)
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

        self._search = SearchPanel(self)
        self._search.search_requested.connect(self.search_text)
        self._search.match_selected.connect(self._on_search_match_selected)
        search_dock = QDockWidget("Buscar", self)
        search_dock.setObjectName("dock_busqueda")
        search_dock.setWidget(self._search)
        search_dock.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
        )
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, search_dock)
        search_dock.hide()
        self._search_dock = search_dock

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

        self._draw_tool_action = QAction("Dibujar", self)
        self._draw_tool_action.setObjectName("accion_dibujar")
        self._draw_tool_action.setCheckable(True)
        self._draw_tool_action.setShortcut(QKeySequence("Ctrl+Shift+D"))
        self._draw_tool_action.setStatusTip("Dibuja trazos libres sobre la página")
        self._draw_tool_action.triggered.connect(lambda: self.set_canvas_tool(CanvasTool.DRAW))

        self._tool_group = QActionGroup(self)
        self._tool_group.setExclusive(True)
        self._tool_group.addAction(self._select_tool_action)
        self._tool_group.addAction(self._region_tool_action)
        self._tool_group.addAction(self._redact_tool_action)
        self._tool_group.addAction(self._draw_tool_action)

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

        self._search_action = QAction("Buscar…", self)
        self._search_action.setObjectName("accion_buscar")
        self._search_action.setShortcut(QKeySequence.StandardKey.Find)
        self._search_action.setStatusTip("Buscar texto en todo el documento")
        self._search_action.triggered.connect(self._show_search)

        self._find_next_action = QAction("Buscar siguiente", self)
        self._find_next_action.setShortcut(QKeySequence.StandardKey.FindNext)
        self._find_next_action.triggered.connect(self.find_next)

        self._find_previous_action = QAction("Buscar anterior", self)
        self._find_previous_action.setShortcut(QKeySequence("Shift+F3"))
        self._find_previous_action.triggered.connect(self.find_previous)

        self._document_info_action = QAction("Información del documento…", self)
        self._document_info_action.setObjectName("accion_informacion_documento")
        self._document_info_action.setShortcut(QKeySequence("Ctrl+Alt+I"))
        self._document_info_action.triggered.connect(self.show_document_info)

        self._rotate_page_action = QAction("Rotar página 90°", self)
        self._rotate_page_action.setObjectName("accion_rotar_pagina")
        self._rotate_page_action.setShortcut(QKeySequence("Ctrl+Alt+R"))
        self._rotate_page_action.triggered.connect(lambda: self.rotate_current_page(90))

        self._move_page_up_action = QAction("Mover página arriba", self)
        self._move_page_up_action.setObjectName("accion_mover_pagina_arriba")
        self._move_page_up_action.setShortcut(QKeySequence("Ctrl+Alt+Up"))
        self._move_page_up_action.triggered.connect(lambda: self.move_current_page(-1))

        self._move_page_down_action = QAction("Mover página abajo", self)
        self._move_page_down_action.setObjectName("accion_mover_pagina_abajo")
        self._move_page_down_action.setShortcut(QKeySequence("Ctrl+Alt+Down"))
        self._move_page_down_action.triggered.connect(lambda: self.move_current_page(1))

        self._delete_page_action = QAction("Eliminar página…", self)
        self._delete_page_action.setObjectName("accion_eliminar_pagina")
        self._delete_page_action.setShortcut(QKeySequence("Ctrl+Alt+Delete"))
        self._delete_page_action.triggered.connect(self.delete_current_page)

        self._extract_pages_action = QAction("Extraer páginas…", self)
        self._extract_pages_action.setObjectName("accion_extraer_paginas")
        self._extract_pages_action.setShortcut(QKeySequence("Ctrl+Alt+E"))
        self._extract_pages_action.triggered.connect(self.extract_pages_dialog)

        self._replace_image_action = QAction("Reemplazar imagen…", self)
        self._replace_image_action.setObjectName("accion_reemplazar_imagen")
        self._replace_image_action.triggered.connect(self.replace_image_dialog)

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
            self._draw_tool_action,
            self._add_text_action,
            self._add_image_action,
            self._undo_action,
            self._redo_action,
            self._delete_action,
            self._search_action,
            self._find_next_action,
            self._find_previous_action,
            self._document_info_action,
            self._rotate_page_action,
            self._move_page_up_action,
            self._move_page_down_action,
            self._delete_page_action,
            self._extract_pages_action,
            self._replace_image_action,
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

        self._stroke_width = QDoubleSpinBox(self)
        self._stroke_width.setObjectName("grosor_trazo")
        self._stroke_width.setRange(0.5, 50.0)
        self._stroke_width.setDecimals(1)
        self._stroke_width.setSingleStep(0.5)
        self._stroke_width.setSuffix(" pt")
        self._stroke_width.setValue(self._stroke_style.width)
        self._stroke_width.setAccessibleName("Grosor del trazo")
        self._stroke_width.setAccessibleDescription(
            "Grosor en puntos del trazo que se dibujará sobre la página."
        )
        self._stroke_width.valueChanged.connect(self._on_stroke_width_changed)

        self._stroke_color_button = QPushButton(self)
        self._stroke_color_button.setObjectName("color_trazo")
        self._stroke_color_button.setAccessibleName("Color del trazo")
        self._stroke_color_button.setAccessibleDescription(
            "Color con el que se dibujarán los trazos nuevos."
        )
        self._stroke_color_button.clicked.connect(self._choose_stroke_color)
        self._update_stroke_color_button()
        self._canvas.set_stroke_style(self._stroke_style)

        toolbar = QToolBar("Principal", self)
        toolbar.setObjectName("toolbar_principal")
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        toolbar.addAction(self._open_action)
        toolbar.addAction(self._export_action)
        toolbar.addAction(self._search_action)
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
        toolbar.addAction(self._draw_tool_action)
        toolbar.addAction(self._add_text_action)
        toolbar.addAction(self._add_image_action)
        toolbar.addAction(self._undo_action)
        toolbar.addAction(self._redo_action)
        toolbar.addAction(self._delete_action)
        self.addToolBar(toolbar)

        drawing_toolbar = QToolBar("Dibujo", self)
        drawing_toolbar.setObjectName("toolbar_dibujo")
        drawing_toolbar.setMovable(False)
        drawing_toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        drawing_toolbar.addAction(self._draw_tool_action)
        drawing_toolbar.addWidget(QLabel("Grosor:", self))
        drawing_toolbar.addWidget(self._stroke_width)
        drawing_toolbar.addWidget(self._stroke_color_button)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, drawing_toolbar)

        file_menu = self.menuBar().addMenu("&Archivo")
        file_menu.addAction(self._open_action)
        file_menu.addAction(self._export_action)
        file_menu.addAction(self._extract_pages_action)
        file_menu.addSeparator()
        file_menu.addAction(self._document_info_action)
        file_menu.addSeparator()
        file_menu.addAction(self._close_action)
        file_menu.addSeparator()
        file_menu.addAction(self._quit_action)

        edit_menu = self.menuBar().addMenu("&Edición")
        edit_menu.addAction(self._undo_action)
        edit_menu.addAction(self._redo_action)
        edit_menu.addSeparator()
        edit_menu.addAction(self._search_action)
        edit_menu.addAction(self._find_next_action)
        edit_menu.addAction(self._find_previous_action)
        edit_menu.addSeparator()
        edit_menu.addAction(self._select_tool_action)
        edit_menu.addAction(self._region_tool_action)
        edit_menu.addAction(self._redact_tool_action)
        edit_menu.addAction(self._draw_tool_action)
        edit_menu.addSeparator()
        edit_menu.addAction(self._add_text_action)
        edit_menu.addAction(self._add_image_action)
        edit_menu.addAction(self._delete_action)

        page_menu = self.menuBar().addMenu("&Página")
        page_menu.addAction(self._rotate_page_action)
        page_menu.addAction(self._move_page_up_action)
        page_menu.addAction(self._move_page_down_action)
        page_menu.addSeparator()
        page_menu.addAction(self._delete_page_action)
        page_menu.addAction(self._extract_pages_action)
        page_menu.addSeparator()
        page_menu.addAction(self._replace_image_action)
        page_menu.addAction(self._document_info_action)

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
        self._page_spin.setRange(1, max(1, self.output_page_count))
        self._page_spin.setValue(self._page_index + 1)
        self._page_spin.blockSignals(False)
        self._page_total.setText(f"/ {self.output_page_count}")
        self._thumbnails.set_current_page(self._page_index)

        self._update_page_status()
        self._status_zoom.setText(f"{self._effective_scale() * 100:.0f} %")
        self._refresh_edit_ui()

    def _update_page_status(self) -> None:
        info = self._document_info
        if info is None:
            return
        source_index = self._source_page_index()
        try:
            page_info = self._page_info(source_index)
        except BeneError as error:
            logger.warning("No se pudo leer la página %d: %s", source_index + 1, error)
            self._status_page.setText("")
            return

        kind = PAGE_KIND_LABELS.get(page_info.kind, "tipo desconocido")
        width, height = rotated_size(
            *page_info.rotated_size,
            self._arrangement().rotation(source_index),
        )
        text = (
            f"Página {self._page_index + 1} de {self.output_page_count} · "
            f"{kind} · {width:.0f} × {height:.0f} pt"
        )
        if self.output_page_count != info.page_count:
            text += f" · original: página {source_index + 1}"
        self._status_page.setText(text)
        self._canvas.setAccessibleDescription(text)

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
        self._edit_session = EditSession(page_count=document.info.page_count)
        self._selected_object_id = None
        self._pending_text = None
        self._pending_image = None
        self._canvas.clear_region()
        self._canvas.set_tool(CanvasTool.SELECT)
        self._select_tool_action.setChecked(True)
        self._clear_search()

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
        self._rebuild_thumbnails()

    def _rebuild_thumbnails(self) -> None:
        document = self._document
        session = self._edit_session
        if document is None or session is None:
            self._thumbnails.set_page_count(0)
            return
        arrangement = session.page_arrangement
        count = arrangement.output_page_count
        self._thumbnails.set_page_count(count)
        requests = [
            ThumbnailRequest(
                arrangement.source_index(position),
                THUMBNAIL_SCALE,
                arrangement.rotation(arrangement.source_index(position)),
            )
            for position in range(count)
        ]
        self._thumbnail_loader.start(self._renderer_factory(document), requests)

    def _on_thumbnail_ready(self, page_index: int, render: object) -> None:
        if not isinstance(render, RenderedPage):
            return
        session = self._edit_session
        position = page_index
        if session is not None:
            mapped = session.page_arrangement.output_index(page_index)
            if mapped is None:
                return
            position = mapped
        self._thumbnails.set_thumbnail(position, rendered_page_to_image(render))

    def _on_thumbnail_failed(self, page_index: int, error: object) -> None:
        logger.warning("Miniatura no disponible para la página %d: %s", page_index + 1, error)

    def _teardown_document(self) -> None:
        self._thumbnail_loader.shutdown()
        self._search_worker.shutdown()
        self._clear_search()
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

    # -------------------------------------------------------------- páginas

    def _arrangement(self) -> PageArrangement:
        session = self._edit_session
        if session is not None:
            return session.page_arrangement
        if self._document_info is not None:
            return PageArrangement.initial(self._document_info.page_count)
        return PageArrangement.initial(0)

    def _source_page_index(self) -> int:
        """Índice de la página original que se está mostrando."""
        arrangement = self._arrangement()
        if arrangement.output_page_count == 0:
            return 0
        position = max(0, min(self._page_index, arrangement.output_page_count - 1))
        return arrangement.source_index(position)

    def _render_rotation(self, source_index: int) -> int:
        extra = self._arrangement().rotation(source_index)
        return (self._view_rotation + extra) % 360

    # ---------------------------------------------------------------- render

    def _effective_scale(self) -> float:
        if self._document_info is None:
            return 1.0
        if self._fit_mode is FitMode.NONE:
            return self._zoom

        try:
            page_info = self._page_info(self._source_page_index())
        except BeneError:
            return self._zoom

        width, height = page_info.rotated_size
        width, height = rotated_size(
            width, height, self._render_rotation(self._source_page_index())
        )
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

        source_index = self._source_page_index()
        rotation = self._render_rotation(source_index)
        key = (source_index, round(scale, 4), rotation)
        cached = self._cache.get(key)
        if cached is not None:
            self._show_render(cached)
            return

        self._status_activity.setText("Renderizando…")
        if not self._canvas.has_image:
            self._canvas.set_message("Renderizando página…")
        self._scheduler.request(source_index, scale, rotation)

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
            width, height = self._page_info(self._source_page_index()).rotated_size
        except BeneError:
            return ratio
        width, height = rotated_size(
            width, height, self._render_rotation(self._source_page_index())
        )
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

        source_index = self._source_page_index()
        expected_rotation = self._render_rotation(source_index)
        if render.page_index != source_index or render.rotation != expected_rotation:
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
        self._refresh_search_highlights()
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
        elif tool is CanvasTool.DRAW:
            self._draw_tool_action.setChecked(True)

    def set_stroke_style(self, style: StrokeStyle) -> None:
        """Actualiza la barra de dibujo y el estilo de los trazos nuevos."""
        self._stroke_style = style
        self._stroke_color = QColor(style.color)
        self._stroke_width.blockSignals(True)
        self._stroke_width.setValue(style.width)
        self._stroke_width.blockSignals(False)
        self._update_stroke_color_button()
        self._canvas.set_stroke_style(style)

    def add_text_object(
        self,
        rect: PdfRect,
        text: str,
        style: TextStyle | None = None,
    ) -> TextObject | None:
        session = self._edit_session
        if session is None or not text.strip():
            return None
        obj = session.add_text(self._source_page_index(), rect, text, style)
        self._selected_object_id = obj.object_id
        self._refresh_edit_ui()
        return obj

    def add_stroke_object(
        self,
        points: Iterable[tuple[float, float]],
        style: StrokeStyle | None = None,
    ) -> StrokeObject | None:
        session = self._edit_session
        if session is None:
            return None
        obj = session.add_stroke(
            self._source_page_index(),
            points,
            style if style is not None else self._stroke_style,
        )
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
            self._source_page_index(),
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
        obj = session.add_redaction(self._source_page_index(), rect)
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

    # ------------------------------------------------------ páginas y búsqueda

    def rotate_current_page(self, degrees: int = 90) -> bool:
        """Acumula una rotación adicional a la página visible."""
        session = self._edit_session
        if session is None or session.output_page_count == 0:
            return False
        source_index = self._source_page_index()
        session.rotate_page(source_index, degrees)
        self._rebuild_thumbnails()
        self._update_ui()
        self._request_render()
        self._status_activity.setText(f"Página rotada {degrees}°; se aplicará al exportar")
        return True

    def move_current_page(self, delta: int) -> bool:
        """Mueve la página visible ``delta`` posiciones en la copia de trabajo."""
        session = self._edit_session
        if session is None:
            return False
        target = self._page_index + delta
        if not 0 <= target < session.output_page_count:
            return False
        session.move_page(self._page_index, target)
        self._page_index = target
        self._selected_object_id = None
        self._rebuild_thumbnails()
        self._update_ui()
        self._request_render()
        self._status_activity.setText("Orden de páginas cambiado; se aplicará al exportar")
        return True

    def delete_current_page(self) -> bool:
        """Elimina la página visible tras confirmarlo (RF-023)."""
        session = self._edit_session
        info = self._document_info
        if session is None or info is None or session.output_page_count <= 1:
            return False

        source_index = self._source_page_index()
        objects = len(session.objects_on_page(source_index))
        detail = (
            f"\n\nTambién se omitirán {objects} objeto(s) añadido(s) en esa página."
            if objects
            else ""
        )
        result = QMessageBox.warning(
            self,
            APP_NAME,
            f"Se eliminará la página {self._page_index + 1} de "
            f"{session.output_page_count} de la copia exportada.{detail}\n\n"
            "El PDF original no cambia y podrás deshacer la eliminación antes de "
            "exportar.\n\n¿Eliminar la página?",
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if result != QMessageBox.StandardButton.Ok:
            return False

        session.delete_page(source_index)
        self._selected_object_id = None
        self._page_index = min(self._page_index, session.output_page_count - 1)
        self._cache.clear()
        self._rebuild_thumbnails()
        self._update_ui()
        self._request_render()
        self._status_activity.setText("Página eliminada; se aplicará al exportar")
        return True

    def extract_pages(self, selection: str, destination: str | Path) -> ExportResult | None:
        """Exporta una selección de páginas visibles sin tocar la sesión."""
        session = self._edit_session
        document = self._document
        info = self._document_info
        if session is None or document is None or info is None:
            return None
        if info.encrypted:
            QMessageBox.warning(
                self,
                APP_NAME,
                "No se puede extraer de un PDF cifrado.\n\n"
                "Guarda antes una copia sin protección y vuelve a abrirla.",
            )
            return None

        positions = parse_page_selection(selection, session.output_page_count)
        sources = tuple(session.page_arrangement.source_index(position) for position in positions)
        arrangement = session.page_arrangement.subset(sources)
        result = self._export_copy(destination, arrangement)
        if result is not None:
            self._status_activity.setText(
                f"Páginas extraídas: {result.destination.name} ({result.page_count} páginas)"
            )
            logger.info(
                "Páginas extraídas a %s (%d páginas)",
                result.destination,
                result.page_count,
            )
        return result

    def extract_pages_dialog(self) -> None:
        session = self._edit_session
        info = self._document_info
        if session is None or info is None:
            return

        text, accepted = QInputDialog.getText(
            self,
            "Extraer páginas",
            f"Páginas a extraer (1-{session.output_page_count}; por ejemplo 1-3, 5):",
        )
        if not accepted or not text.strip():
            return
        try:
            parse_page_selection(text, session.output_page_count)
        except BeneError as error:
            QMessageBox.warning(self, APP_NAME, str(error))
            return

        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Extraer páginas",
            str(self._default_extract_path(info)),
            "Documentos PDF (*.pdf)",
        )
        if not filename:
            return
        destination = Path(filename)
        if destination.suffix.lower() != ".pdf":
            destination = destination.with_suffix(".pdf")
        result = self.extract_pages(text, destination)
        if result is not None:
            QMessageBox.information(
                self,
                APP_NAME,
                f"Se han extraído {result.page_count} páginas en:\n{result.destination}",
            )

    def show_document_info(self) -> None:
        info = self._document_info
        if info is None:
            return
        dialog = DocumentInfoDialog(
            info,
            page_size=self._page_size(),
            output_page_count=self.output_page_count,
            parent=self,
        )
        dialog.exec()

    def replace_image_object(
        self,
        image_id: str,
        rect: PdfRect,
        data: bytes,
        mime_type: str,
        *,
        source_path: Path | None = None,
    ) -> ImageReplacementObject | None:
        session = self._edit_session
        if session is None:
            return None
        obj = session.replace_image(
            self._source_page_index(),
            image_id,
            rect,
            data,
            mime_type,
            source_path=source_path,
        )
        self._selected_object_id = obj.object_id
        self._refresh_edit_ui()
        return obj

    def replace_image_dialog(self) -> None:
        document = self._document
        session = self._edit_session
        if document is None or session is None:
            return

        source_index = self._source_page_index()
        try:
            images = document.images_on_page(source_index)
        except BeneError as error:
            self._show_error(error)
            return
        if not images:
            QMessageBox.information(
                self,
                APP_NAME,
                "No se han detectado imágenes reemplazables en esta página.\n\n"
                "Las imágenes en línea, las que están dentro de formularios o las "
                "que el PDF no identifica de forma fiable no se pueden sustituir.",
            )
            return

        dialog = ImageReplacementDialog(
            images,
            self,
            last_directory=self._last_directory,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        image = dialog.selected_image
        loaded = dialog.replacement
        if image is None or loaded is None:
            return

        self.replace_image_object(
            image.image_id,
            image.rect,
            loaded.data,
            loaded.mime_type,
            source_path=loaded.source_path,
        )
        self._last_directory = loaded.source_path.parent
        self._status_activity.setText("Imagen marcada para reemplazar; se aplicará al exportar")

    def _show_search(self) -> None:
        if self._document is None:
            return
        self._search_dock.show()
        self._search_dock.raise_()
        self._search.focus_query()

    def search_text(self, query: str) -> None:
        """Busca ``query`` en todo el documento y muestra los resultados."""
        document = self._document
        text = query.strip()
        if document is None or not text:
            return
        self._search_dock.show()
        self._search.set_searching(text)
        self._search_worker.search(document, text)

    def find_next(self) -> None:
        if not self._search_matches:
            self._show_search()
            return
        self._search.next_match()

    def find_previous(self) -> None:
        if not self._search_matches:
            self._show_search()
            return
        self._search.previous_match()

    def _on_search_ready(self, query: str, matches: object) -> None:
        if isinstance(matches, Iterable):
            result = tuple(match for match in matches if isinstance(match, SearchMatch))
        else:
            result = ()
        self._search_matches = result
        self._current_search_match = None
        self._search.set_results(query, result)
        self._refresh_search_highlights()

    def _on_search_failed(self, query: str, error: object) -> None:
        self._search_matches = ()
        self._current_search_match = None
        self._search.set_error(query, str(error))
        self._canvas.clear_search_highlights()

    def _on_search_match_selected(self, match: object) -> None:
        if not isinstance(match, SearchMatch):
            return
        position = self._arrangement().output_index(match.page_index)
        if position is None:
            self._status_activity.setText(
                "La coincidencia está en una página eliminada de la copia de trabajo"
            )
            return
        self._current_search_match = match
        if position != self._page_index:
            self._page_index = position
            self._selected_object_id = None
            self._update_ui()
            self._request_render()
        else:
            self._refresh_search_highlights()

    def _refresh_search_highlights(self) -> None:
        if self._document_info is None:
            self._canvas.clear_search_highlights()
            return
        source_index = self._source_page_index()
        rects = tuple(
            match.rect for match in self._search_matches if match.page_index == source_index
        )
        current = self._current_search_match
        if current is not None and current.page_index != source_index:
            current = None
        self._canvas.set_search_highlights(rects, current.rect if current else None)

    def _clear_search(self) -> None:
        self._search_matches = ()
        self._current_search_match = None
        self._search.clear()
        self._canvas.clear_search_highlights()

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
            self._update_page_actions(None)
            return

        source_index = self._source_page_index()
        selected = (
            session.object(self._selected_object_id)
            if self._selected_object_id is not None
            else None
        )
        if selected is not None and selected.page_index != source_index:
            self._selected_object_id = None
            selected = None

        page_objects = session.objects_on_page(source_index)
        self._canvas.set_objects(page_objects)
        self._canvas.set_overflow_ids(self._overflow_ids(page_objects))
        self._properties.set_object(selected)
        self._undo_action.setEnabled(session.can_undo)
        self._redo_action.setEnabled(session.can_redo)
        self._delete_action.setEnabled(selected is not None)
        self._status_edit.setText("Cambios sin exportar" if session.is_dirty else "Sin cambios")
        if self._canvas.selected_object_id != self._selected_object_id:
            self._canvas.select_object(self._selected_object_id)
        self._update_page_actions(session)

    def _update_page_actions(self, session: EditSession | None) -> None:
        if session is None:
            for action in (
                self._rotate_page_action,
                self._move_page_up_action,
                self._move_page_down_action,
                self._delete_page_action,
                self._extract_pages_action,
                self._replace_image_action,
            ):
                action.setEnabled(False)
            return

        count = session.output_page_count
        self._rotate_page_action.setEnabled(count > 0)
        self._move_page_up_action.setEnabled(count > 1 and self._page_index > 0)
        self._move_page_down_action.setEnabled(count > 1 and self._page_index < count - 1)
        self._delete_page_action.setEnabled(count > 1)
        self._extract_pages_action.setEnabled(count > 0)
        self._replace_image_action.setEnabled(count > 0)

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

    def _on_stroke_requested(self, points: object, style: object) -> None:
        if not isinstance(points, tuple) or not points:
            return
        stroke_style = style if isinstance(style, StrokeStyle) else self._stroke_style
        if self.add_stroke_object(points, stroke_style) is not None:
            self._status_activity.setText("Trazo añadido")

    def _on_stroke_width_changed(self, value: float) -> None:
        self.set_stroke_style(StrokeStyle(color=self._stroke_color.name(), width=value))

    def _choose_stroke_color(self) -> None:
        color = QColorDialog.getColor(self._stroke_color, self, "Color del trazo")
        if color.isValid():
            self._stroke_color = color
            self.set_stroke_style(StrokeStyle(color=color.name(), width=self._stroke_width.value()))

    def _update_stroke_color_button(self) -> None:
        contrast = "#000000" if self._stroke_color.lightness() > 128 else "#ffffff"
        self._stroke_color_button.setText(self._stroke_color.name())
        self._stroke_color_button.setStyleSheet(
            f"background-color: {self._stroke_color.name()}; color: {contrast};"
        )

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
        dialog = TextDialog(self, style=self._last_text_style)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._last_text_style = dialog.chosen_style
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
            return self._page_info(self._source_page_index()).rotated_size
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
                arrangement=session.page_arrangement,
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
            "Documento exportado a %s (%d redacciones, %d textos, %d imágenes, "
            "%d reemplazos de imagen, %d trazos)",
            result.destination,
            result.redaction_count,
            result.text_count,
            result.image_count,
            result.replacement_count,
            result.stroke_count,
        )
        return result

    def _export_copy(
        self,
        destination: str | Path,
        arrangement: PageArrangement,
    ) -> ExportResult | None:
        """Exporta una copia con una disposición concreta sin tocar la sesión.

        Se usa para extraer páginas: no marca la sesión como guardada ni cambia
        el historial, porque el documento de trabajo sigue siendo el mismo.
        """
        document = self._document
        session = self._edit_session
        if document is None or session is None:
            return None
        try:
            return self._export_document(
                document,
                destination,
                objects=session.objects,
                arrangement=arrangement,
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

    def _default_export_path(self, info: DocumentInfo) -> Path:
        """Nombre de exportación que no pisa una copia anterior."""
        candidate = info.path.with_name(f"{info.path.stem}-editado.pdf")
        index = 2
        while candidate.exists():
            candidate = info.path.with_name(f"{info.path.stem}-editado-{index}.pdf")
            index += 1
        return candidate

    def _default_extract_path(self, info: DocumentInfo) -> Path:
        """Nombre de extracción que no pisa un archivo anterior."""
        candidate = info.path.with_name(f"{info.path.stem}-paginas.pdf")
        index = 2
        while candidate.exists():
            candidate = info.path.with_name(f"{info.path.stem}-paginas-{index}.pdf")
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
