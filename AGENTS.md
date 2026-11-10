# AGENTS.md

Guía para sesiones de OpenCode en este repositorio. El producto, la interfaz, `PLAN.md`, los ADR y los mensajes de commit están en español; `README.md` es la guía principal en inglés y `README.es.md` la versión española.

## Comandos

El proyecto se desarrolla en Windows con Python 3.12. Ejecuta los comandos desde la raíz del repositorio. Desde WSL usa los ejecutables del venv, no `source .venv/bin/activate`:

```bash
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m pytest tests/unit/test_pages.py::test_name -q
.venv/Scripts/python.exe -m pytest -m slow          # documentos de 100 páginas y rendimiento
.venv/Scripts/ruff.exe check .
.venv/Scripts/ruff.exe format --check .
.venv/Scripts/mypy.exe
```

`pytest` excluye `slow` por defecto (`addopts = -m 'not slow'`); `-m ui` ejecuta solo interfaz y `conftest.py` fija `QT_QPA_PLATFORM=offscreen`. Antes de terminar: `ruff check`, `ruff format --check`, `mypy` y `pytest -q`; si tocas exportación, render o páginas, añade `pytest -q -m slow`. CI ejecuta en ese mismo orden en Windows y Ubuntu, más cobertura, pruebas lentas y build en Windows.

Instalación: `python -m pip install -e ".[dev]"`. Build: instala el extra `build` con `python -m pip install -e ".[dev,build]"` y ejecuta `python scripts/build_app.py` (`--dry-run` muestra el comando; `--onefile` genera un único ejecutable). `scripts/verify_env.py` comprueba Python, PyMuPDF y Qt offscreen.

## Arquitectura y fronteras

- `domain/` no importa capas externas ni Qt/PyMuPDF. `application/` no importa infraestructura, presentación, `bootstrap` ni `main`. `presentation/` no importa PyMuPDF.
- `pymupdf` y `fitz` solo se importan en `src/bene/infrastructure/pdf/pymupdf_engine.py`; `PySide6` solo en `presentation/` y `main.py`. `tests/unit/test_architecture.py` lo verifica.
- `bootstrap.create_application()` es el composition root; `main.py` solo crea `QApplication` y arranca. El motor se inyecta mediante el puerto `PdfEngine`.
- Renders, miniaturas y búsquedas usan `QThreadPool`. PyMuPDF no es seguro entre hilos y el adaptador lo serializa con un cerrojo; no accedas al documento desde el hilo de UI.

## Invariantes que no son obvios

- La edición vive solo en memoria: el PDF original nunca se modifica. La exportación escribe a un temporal, lo reabre para validarlo y reemplaza el destino de forma atómica; rechaza un destino igual al origen.
- En `PageArrangement`, `order` y `rotations` usan índices **fuente** (base cero), no posiciones de salida. Una página ausente de `order` está eliminada. En la UI, `MainWindow._page_index` es posición de salida: usa `_source_page_index()` antes de tocar objetos o páginas.
- `EditSession` reconstruye objetos y disposición reproduciendo todos los comandos activos; los comandos de objeto y de página comparten historial. `is_dirty` compara la tupla de comandos, no solo su número.
- `PageArrangement.rotations` es un `MappingProxyType`; no lo mutéis. La rotación de vista es solo visual; la rotación adicional de página se aplica al exportar.
- Orden de exportación: redacciones/ediciones → rotación adicional → `document.select(order)`. No reordenes estos pasos.
- `page.rect` ya aplica `/Rotate`. `PageInfo` guarda dimensiones sin rotar y `rotated_size` aplica la rotación. Las coordenadas de `search_for` y `get_image_info` son sin rotar y se convierten con `rect * page.rotation_matrix`.
- La redacción debe eliminar el contenido subyacente (hay pruebas de no extracción) y pedir confirmación; no la conviertas en una caja negra.
- Nunca registres el texto del documento ni contraseñas. El registro rota a 2 MB y conserva tres copias.

## Pruebas y UI

- Los PDFs de prueba son sintéticos y se generan al vuelo en `tests/integration/synthetic.py`; no hay binarios de fixtures. `tests/integration/test_large_document.py` genera 100 páginas y está marcado `slow`.
- `tests/conftest.py` limpia `EditSession` en el teardown para que el diálogo modal de cambios sin exportar no bloquee `pytest-qt`. No crees `QApplication` a mano en las pruebas.
- `QAction.triggered` emite un `bool`: usa `lambda` si el método conectado recibe argumentos.
- `mypy` analiza `src` y `tests` con `warn_unused_ignores`; no dejes `# type: ignore` innecesarios. CI resuelve PyMuPDF 2.1 y el venv local tiene 2.0; 2.0 no anota algunas constantes que 2.1 sí. Usa los auxiliares `_pdf_constant`/`_pymupdf_constant` (`getattr`) en vez de añadir ignores por versión.
- La UI, los docstrings, los comentarios y los mensajes están en español; mantén ese idioma. Si cambias el README, sincroniza `README.md` y `README.es.md`.

## Documentación

`README.md`, `README.es.md`, `PLAN.md` y `docs/decisions/ADR-*.md` son las fuentes de contexto. Actualiza `PLAN.md` (estado y bitácora) y el ADR correspondiente cuando cambies decisiones o comportamiento.
