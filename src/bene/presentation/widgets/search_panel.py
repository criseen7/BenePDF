"""Panel de búsqueda de texto con navegación entre coincidencias (RF-020)."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from bene.application.ports.pdf_engine import SearchMatch


class SearchPanel(QWidget):
    """Campo de búsqueda, lista de resultados y botones de navegación."""

    search_requested = Signal(str)
    match_selected = Signal(object)  # SearchMatch

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._matches: tuple[SearchMatch, ...] = ()
        self._current = -1
        self._query = ""

        self.setObjectName("panel_busqueda")
        self.setAccessibleName("Búsqueda de texto")

        self._query_edit = QLineEdit(self)
        self._query_edit.setObjectName("campo_busqueda")
        self._query_edit.setPlaceholderText("Buscar en el documento…")
        self._query_edit.setAccessibleName("Texto a buscar")
        self._query_edit.setClearButtonEnabled(True)
        self._query_edit.returnPressed.connect(self._request_search)

        self._search_button = QPushButton("Buscar", self)
        self._search_button.setObjectName("boton_buscar")
        self._search_button.clicked.connect(self._request_search)

        self._status = QLabel("Escribe un texto y pulsa Buscar", self)
        self._status.setObjectName("estado_busqueda")
        self._status.setWordWrap(True)

        self._results = QListWidget(self)
        self._results.setObjectName("resultados_busqueda")
        self._results.setAccessibleName("Resultados de búsqueda")
        self._results.setAlternatingRowColors(True)
        self._results.itemActivated.connect(self._on_item_activated)
        self._results.itemClicked.connect(self._on_item_activated)

        self._previous_button = QPushButton("Anterior", self)
        self._previous_button.setObjectName("boton_busqueda_anterior")
        self._previous_button.clicked.connect(self.previous_match)

        self._next_button = QPushButton("Siguiente", self)
        self._next_button.setObjectName("boton_busqueda_siguiente")
        self._next_button.clicked.connect(self.next_match)

        navigation = QHBoxLayout()
        navigation.addWidget(self._previous_button)
        navigation.addWidget(self._next_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(self._query_edit)
        layout.addWidget(self._search_button)
        layout.addWidget(self._status)
        layout.addWidget(self._results, 1)
        layout.addLayout(navigation)

        self._update_navigation()

    # ------------------------------------------------------------- propiedades

    @property
    def query(self) -> str:
        return self._query_edit.text()

    @property
    def matches(self) -> tuple[SearchMatch, ...]:
        return self._matches

    @property
    def current_match(self) -> SearchMatch | None:
        if 0 <= self._current < len(self._matches):
            return self._matches[self._current]
        return None

    @property
    def current_index(self) -> int:
        return self._current

    @property
    def status_text(self) -> str:
        return self._status.text()

    # ----------------------------------------------------------------- estado

    def focus_query(self) -> None:
        self._query_edit.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self._query_edit.selectAll()

    def set_query(self, query: str) -> None:
        self._query_edit.setText(query)

    def set_searching(self, query: str) -> None:
        self._query = query
        self._status.setText(f"Buscando «{query}»…")
        self._search_button.setEnabled(False)

    def set_results(self, query: str, matches: tuple[SearchMatch, ...]) -> None:
        self._query = query
        self._search_button.setEnabled(True)
        self._matches = tuple(matches)
        self._current = -1
        self._results.clear()

        for index, match in enumerate(self._matches):
            snippet = match.snippet.strip() or query
            item = QListWidgetItem(f"Página {match.page_index + 1} · {snippet}")
            item.setData(Qt.ItemDataRole.UserRole, index)
            item.setToolTip(snippet)
            self._results.addItem(item)

        if not self._matches:
            self._status.setText(f"Sin coincidencias para «{query}»")
        elif len(self._matches) == 1:
            self._status.setText("1 coincidencia")
        else:
            self._status.setText(f"{len(self._matches)} coincidencias")

        self._update_navigation()
        if self._matches:
            self._select(0)

    def set_error(self, query: str, message: str) -> None:
        self._query = query
        self._search_button.setEnabled(True)
        self._matches = ()
        self._current = -1
        self._results.clear()
        self._status.setText(f"No se pudo buscar: {message}")
        self._update_navigation()

    def clear(self) -> None:
        self._matches = ()
        self._current = -1
        self._query = ""
        self._results.clear()
        self._status.setText("Escribe un texto y pulsa Buscar")
        self._search_button.setEnabled(True)
        self._update_navigation()

    def next_match(self) -> None:
        if not self._matches:
            return
        self._select((self._current + 1) % len(self._matches))

    def previous_match(self) -> None:
        if not self._matches:
            return
        self._select((self._current - 1) % len(self._matches))

    # -------------------------------------------------------------- internos

    def _request_search(self) -> None:
        query = self._query_edit.text().strip()
        if not query:
            self._status.setText("Escribe un texto para buscar")
            return
        self.search_requested.emit(query)

    def _select(self, index: int) -> None:
        if not 0 <= index < len(self._matches):
            return
        self._current = index
        self._results.blockSignals(True)
        self._results.setCurrentRow(index)
        self._results.blockSignals(False)
        self._results.scrollToItem(self._results.item(index))
        match = self._matches[index]
        self._status.setText(
            f"Coincidencia {index + 1} de {len(self._matches)} · página {match.page_index + 1}"
        )
        self._update_navigation()
        self.match_selected.emit(match)

    def _on_item_activated(self, item: QListWidgetItem) -> None:
        index = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(index, int):
            self._select(index)

    def _update_navigation(self) -> None:
        enabled = bool(self._matches)
        self._previous_button.setEnabled(enabled)
        self._next_button.setEnabled(enabled)
