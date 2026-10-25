"""Composición de dependencias y arranque de la aplicación."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from bene.application.use_cases.open_document import OpenDocument
from bene.application.use_cases.render_page import RenderPage
from bene.config import APP_NAME, AppPaths
from bene.infrastructure.logging.setup import configure_logging
from bene.infrastructure.pdf.pymupdf_engine import PyMuPDFEngine
from bene.presentation.main_window import MainWindow

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class Application:
    paths: AppPaths
    main_window: MainWindow


def create_application(*, paths: AppPaths | None = None) -> Application:
    """Construye la aplicación completa. Requiere una ``QApplication`` previa."""
    resolved_paths = paths if paths is not None else AppPaths.default()
    log_path = configure_logging(resolved_paths.log_dir)

    logger.info("Iniciando %s", APP_NAME)
    logger.info("Registro técnico en %s", log_path)

    engine = PyMuPDFEngine()
    window = MainWindow(
        open_document=OpenDocument(engine),
        renderer_factory=RenderPage,
    )
    return Application(paths=resolved_paths, main_window=window)
