"""Pruebas del registro técnico rotativo (RNF-015)."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from logging.handlers import RotatingFileHandler
from pathlib import Path

import pytest

from bene.infrastructure.logging.setup import (
    BACKUP_COUNT,
    LOG_FILENAME,
    MAX_BYTES,
    configure_logging,
    reset_logging,
)


@pytest.fixture(autouse=True)
def restore_logging() -> Iterator[None]:
    """Deja el registro raíz como estaba antes de cada prueba."""
    root = logging.getLogger()
    previous_level = root.level
    reset_logging()
    try:
        yield
    finally:
        reset_logging()
        root.setLevel(previous_level)


def test_crea_el_directorio_y_el_archivo(tmp_path: Path) -> None:
    log_dir = tmp_path / "registros" / "anidado"

    log_path = configure_logging(log_dir)

    assert log_path == log_dir / LOG_FILENAME
    assert log_path.parent.is_dir()
    assert log_path.is_file()


def test_escribe_los_mensajes(tmp_path: Path) -> None:
    log_path = configure_logging(tmp_path)
    logger = logging.getLogger("bene.prueba")

    logger.info("Documento abierto")
    logger.warning("Página no renderizada")

    content = log_path.read_text(encoding="utf-8")
    assert "INFO" in content
    assert "bene.prueba: Documento abierto" in content
    assert "WARNING" in content
    assert "Página no renderizada" in content


def test_configura_la_rotacion(tmp_path: Path) -> None:
    log_path = configure_logging(tmp_path)

    handlers = [
        handler
        for handler in logging.getLogger().handlers
        if isinstance(handler, RotatingFileHandler) and Path(handler.baseFilename) == log_path
    ]

    assert len(handlers) == 1
    assert handlers[0].maxBytes == MAX_BYTES
    assert handlers[0].backupCount == BACKUP_COUNT


def test_es_idempotente(tmp_path: Path) -> None:
    configure_logging(tmp_path)
    log_path = configure_logging(tmp_path)

    logging.getLogger("bene.prueba").info("mensaje único")

    content = log_path.read_text(encoding="utf-8")
    assert content.count("mensaje único") == 1
    assert (
        len(
            [
                handler
                for handler in logging.getLogger().handlers
                if isinstance(handler, RotatingFileHandler)
            ]
        )
        == 1
    )


def test_ajusta_el_nivel_raiz(tmp_path: Path) -> None:
    configure_logging(tmp_path, level=logging.DEBUG)

    assert logging.getLogger().level == logging.DEBUG


def test_reset_desconecta_los_manejadores(tmp_path: Path) -> None:
    configure_logging(tmp_path)
    root = logging.getLogger()
    assert any(isinstance(handler, RotatingFileHandler) for handler in root.handlers)

    reset_logging()

    assert not any(isinstance(handler, RotatingFileHandler) for handler in root.handlers)
    reset_logging()


def test_no_duplica_manejadores_tras_reset(tmp_path: Path) -> None:
    configure_logging(tmp_path)
    reset_logging()
    log_path = configure_logging(tmp_path)

    logging.getLogger("bene.prueba").info("después del reinicio")

    content = log_path.read_text(encoding="utf-8")
    assert content.count("después del reinicio") == 1
