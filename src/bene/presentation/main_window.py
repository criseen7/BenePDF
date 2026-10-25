"""Ventana principal de Bene PDF (RF-001 a RF-005, RF-017)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Final

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import (
    QAction,
    QCloseEvent,
    QDragEnterEvent,
    QDropEvent,
    QKeySequence,
    QResizeEvent,
)
from PySide6.QtWidgets import (
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
from bene.application.use_cases.open_document import OpenDocument
from bene.config import APP_NAME
from bene.domain.errors import BeneError, EncryptedDocumentError
from bene.domain.models import DocumentInfo, PageInfo, PageKind
from bene.presentation.fit import FitMode, clamp_scale, fit_scale, next_zoom, rotated_size
from bene.presentation.render_cache import RenderCache
from bene.presentation.viewer.pdf_canvas import PdfCanvas, rendered_page_to_image
from bene.presentation.widgets.thumbnail_panel import ThumbnailPanel
from bene.presentation.workers.render_worker import PageRenderer, RenderScheduler
from bene.presentation.workers.thumbnail_worker import ThumbnailLoader, ThumbnailRequest

logger = logging.getLogger(__name__)

MAX_PASSWORD_ATTEMPTS: Final[int] = 3
RESIZE_DEBOUNCE_MS: Final[int] = 150
THUMBNAIL_SCALE: Final[float] = 0.2

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

        self._document: OpenedDocument | None = None
        self._document_info: DocumentInfo | None = None
        self._scheduler: RenderScheduler | None = None
        self._page_infos: dict[int, PageInfo] = {}
        self._cache = RenderCache()
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

            self._install_document(document, candidate)
            return True

    def go_to_page(self, page_index: int) -> None:
        if self._document_info is None:
            return
        target = max(0, min(page_index, self._document_info.page_count - 1))
        self._page_index = target
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
        self._teardown_document()
        self._update_ui()

    # ------------------------------------------------------------------- UI

    def _build_ui(self) -> None:
        self.setWindowTitle(APP_NAME)
        self.resize(1100, 850)
        self.setAcceptDrops(True)

        self._canvas = PdfCanvas()
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

        self._open_action = QAction("Abrir…", self)
        self._open_action.setShortcut(QKeySequence.StandardKey.Open)
        self._open_action.setStatusTip("Abrir un documento PDF")
        self._open_action.triggered.connect(self._choose_file)

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
        self._rotate_action.triggered.connect(self.rotate_view)

        self._close_action = QAction("Cerrar documento", self)
        self._close_action.setShortcut(QKeySequence("Ctrl+W"))
        self._close_action.triggered.connect(self.close_document)

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
        )

        self._page_spin = QSpinBox(self)
        self._page_spin.setRange(1, 1)
        self._page_spin.setFixedWidth(76)
        self._page_spin.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._page_spin.valueChanged.connect(self._on_page_spin_changed)

        self._page_total = QLabel("/ 0", self)

        self._previous_button = QToolButton(self)
        self._previous_button.setText("◀")
        self._previous_button.setToolTip("Página anterior (RePág)")
        self._previous_button.setShortcut(QKeySequence("PgUp"))
        self._previous_button.clicked.connect(self.previous_page)

        self._next_button = QToolButton(self)
        self._next_button.setText("▶")
        self._next_button.setToolTip("Página siguiente (AvPág)")
        self._next_button.setShortcut(QKeySequence("PgDown"))
        self._next_button.clicked.connect(self.next_page)

        toolbar = QToolBar("Principal", self)
        toolbar.setObjectName("toolbar_principal")
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        toolbar.addAction(self._open_action)
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
        self.addToolBar(toolbar)

        file_menu = self.menuBar().addMenu("&Archivo")
        file_menu.addAction(self._open_action)
        file_menu.addAction(self._close_action)
        file_menu.addSeparator()
        file_menu.addAction(self._quit_action)

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

        status = self.statusBar()
        status.addWidget(self._status_document, 1)
        status.addPermanentWidget(self._status_page)
        status.addPermanentWidget(self._status_activity)
        status.addPermanentWidget(self._status_zoom)

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
            return

        info = self._document_info
        assert info is not None

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
        self._canvas.set_image(None)
        self._thumbnails.set_page_count(0)

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

        scale = self._effective_scale()
        self._status_zoom.setText(f"{scale * 100:.0f} %")

        key = (self._page_index, round(scale, 4), self._view_rotation)
        cached = self._cache.get(key)
        if cached is not None:
            self._show_render(cached)
            return

        self._status_activity.setText("Renderizando…")
        if not self._canvas.has_image:
            self._canvas.set_message("Renderizando página…")
        self._scheduler.request(self._page_index, scale, self._view_rotation)

    def _on_rendered(self, render: object) -> None:
        if not isinstance(render, RenderedPage):
            return

        key = (render.page_index, round(render.scale, 4), render.rotation)
        self._cache.put(key, render)

        if render.page_index != self._page_index or render.rotation != self._view_rotation:
            return
        if abs(render.scale - self._effective_scale()) > 0.01:
            return

        self._show_render(render)

    def _on_render_failed(self, error: object) -> None:
        logger.warning("Error al renderizar: %s", error)
        self._status_activity.setText("No se pudo renderizar la página")
        if not self._canvas.has_image:
            self._canvas.set_message("No se pudo renderizar la página")
        QMessageBox.warning(self, APP_NAME, f"No se pudo renderizar la página.\n\n{error}")

    def _show_render(self, render: RenderedPage) -> None:
        self._canvas.set_image(rendered_page_to_image(render))
        self._status_activity.setText("Listo")
        self._update_page_status()

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
