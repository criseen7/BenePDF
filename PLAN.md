# PLAN — Bene

- **Estado:** iteración 1 en curso
- **Última actualización:** 2026-10-24
- **Especificación de referencia:** [docs/requirements.md](docs/requirements.md)

## 1. Decisiones adoptadas

| Tema | Decisión | Motivo |
|---|---|---|
| Nombre | **Bene** (provisional) | Elegido por el usuario; paquete Python `bene`, comando `bene` |
| Distribución | Uso personal, sin distribución | Permite usar PyMuPDF bajo AGPL sin obligaciones de distribución |
| Lenguaje | Python 3.12 (Windows nativo) | Es la versión instalada en la máquina objetivo y la que soportan todas las ruedas |
| Interfaz | PySide6 6.12, textos en español | Qt cubre visor, diálogos y tareas en segundo plano; licencia LGPL |
| Motor PDF | PyMuPDF 2.0 (`pymupdf`) tras el puerto `PdfEngine` | Render, inserción de texto e imágenes y redacción real con una sola dependencia |
| Modelo de edición | Comandos inmutables en memoria; el PDF fuente nunca se modifica | Deshacer/rehacer correcto y cumplimiento de RN-001 y RN-008 |
| Persistencia | Nada se guarda hasta exportar; la exportación escribe a temporal y valida | Integridad del archivo original (RNF-005) |
| Miniaturas | Iteración 2 | Mantener la primera iteración pequeña y verificable |

Las decisiones con consecuencias arquitectónicas se documentan en `docs/decisions/`.

## 2. Iteración 1 — esqueleto funcional

**Objetivo verificable:** abrir un PDF, ver la primera página en menos de 3 s, navegar, aplicar zoom/ajuste/rotación de vista y clasificar la página (texto, gráfico o escaneada) sin bloquear la interfaz y con el motor PDF aislado tras un puerto.

### Paso 0 — Base del proyecto

- [x] Repositorio git inicializado con `.gitignore` y `.gitattributes`
- [x] `pyproject.toml` con dependencias fijadas, extras `dev`, entry point `bene`
- [x] Ruff (lint y formato) y mypy configurados
- [x] pytest + pytest-qt configurados
- [x] `README.md` con requisitos e instrucciones
- [x] Requisitos movidos a `docs/requirements.md`
- [x] `ADR-001` (motor PDF) y `ADR-002` (modelo de edición)
- [x] Entorno virtual en Windows con dependencias instaladas y verificadas

Verificación reproducible: `scripts/verify_env.py` comprueba la versión de Python, que PyMuPDF elimina realmente el texto redactado y que Qt dibuja en modo offscreen. Resultado en esta máquina: Python 3.12.1, pymupdf 2.0 y Qt 6.12.0, todo correcto.

### Paso 1 — Dominio y puerto

- [x] `domain/models.py`: `DocumentInfo`, `PageInfo`, `PdfRect`, `PageKind`
- [x] `domain/errors.py`: errores de apertura, cifrado, render y rango de página
- [x] `application/ports/pdf_engine.py`: `Protocol` + DTO `RenderedPage`, sin tipos de PyMuPDF

Los modelos validan sus invariantes al construirse (`PdfRect` rechaza coordenadas
invertidas o no finitas; `PageInfo` valida rotación y recuentos). `PageKind`
distingue vacía, texto, gráfico y escaneada. El puerto separa la fábrica
(`PdfEngine.open_document`) de la sesión (`OpenedDocument`), que declara
explícitamente quién cierra el documento.

### Paso 2 — Adaptador PyMuPDF

- [ ] `infrastructure/pdf/pymupdf_engine.py`, único módulo que importa `pymupdf`
- [ ] Render RGB888 con matriz de escala
- [ ] Contraseña en memoria para PDF cifrados; detección de texto/escaneado
- [ ] Traducción de errores de MuPDF a errores de dominio

### Paso 3 — Casos de uso

- [ ] `open_document.py`: validación de ruta, extensión y tamaño máximo
- [ ] `render_page.py`: validación de índice y zoom

### Paso 4 — Presentación

- [ ] `main_window.py`: barra superior, visor y barra de estado
- [ ] `viewer/pdf_canvas.py`: widget que pinta el `QImage`
- [ ] Render en `QThreadPool` con descarte de resultados obsoletos
- [ ] Caché LRU acotada por número de páginas y memoria
- [ ] Abrir desde diálogo y arrastrando archivos; contraseña para PDF cifrados

### Paso 5 — Infraestructura transversal

- [ ] `bootstrap.py` como composition root
- [ ] Logging rotativo en `%LOCALAPPDATA%\EditorPDF\logs`, sin texto del documento
- [ ] Rutas de configuración vía `QStandardPaths`

### Paso 6 — Pruebas

- [ ] Unitarias con `FakePdfEngine`: validaciones y casos de uso
- [ ] Integración contra PDFs sintéticos generados en el test
- [ ] Smoke test de UI con `QT_QPA_PLATFORM=offscreen`
- [ ] Test de frontera: `pymupdf` solo en `infrastructure/pdf`; `PySide6` solo en `presentation` y `main.py`
- [ ] Benchmark manual con PDF de 100 páginas (< 3 s la primera página)

## 3. Estructura objetivo

```text
EditorPDF-Local/
├── PLAN.md
├── README.md
├── pyproject.toml
├── docs/
│   ├── requirements.md
│   └── decisions/
│       ├── ADR-001-motor-pdf.md
│       └── ADR-002-modelo-de-edicion.md
├── src/bene/
│   ├── main.py
│   ├── bootstrap.py
│   ├── config.py
│   ├── domain/
│   ├── application/
│   │   ├── ports/
│   │   └── use_cases/
│   ├── infrastructure/
│   │   ├── pdf/
│   │   └── logging/
│   └── presentation/
│       ├── main_window.py
│       ├── viewer/
│       └── workers/
└── tests/
    ├── unit/
    ├── integration/
    ├── ui/
    └── fixtures/
```

## 4. Criterios de verificación de la iteración 1

1. `pytest` en verde en Windows (unitarias, integración y UI offscreen).
2. `ruff check` y `ruff format --check` sin errores.
3. `mypy` sin errores en dominio, aplicación e infraestructura.
4. PDF real de 100 páginas: primera página en menos de 3 s y navegación sin bloqueos.
5. PDF corrupto, cifrado y escaneado: mensajes claros y sin cierre inesperado.
6. El log existe, rota y no contiene texto del documento.

## 5. Riesgos abiertos

| Riesgo | Impacto | Mitigación |
|---|---|---|
| PyMuPDF 2.0 es muy reciente | Alto | Versión fijada `>=2.0,<3`; plan B: `1.28.2` con el parche de redacción |
| La vista previa por capas no reproduce el resultado exacto | Medio | Botón de vista previa exacta aplicando comandos a una copia en memoria |
| Redacción puede eliminar objetos solapados | Alto | Vista previa con la zona marcada, confirmación explícita y pruebas con objetos cercanos |
| Rendimiento en PDF escaneados de gran tamaño | Medio | Render bajo demanda, caché acotada y tareas en segundo plano |

## 6. Backlog posterior

| Iteración | Contenido |
|---|---|
| 2 | Miniaturas, selección de región, conversión de coordenadas, añadir texto e imágenes, mover/redimensionar, historial deshacer/rehacer |
| 3 | Redacción permanente con confirmación, exportación a temporal con validación y pruebas de no extracción |
| 4 | Mensajes de error, accesibilidad, PDFs rotados y grandes, empaquetado con PyInstaller |
| 5 | OCR local opcional, búsqueda, operaciones de páginas |

## 7. Bitácora

| Fecha | Avance |
|---|---|
| 2026-10-24 | Análisis de requisitos y plan acordado. Paso 0 ejecutado: proyecto, herramientas, docs y entorno verificado. |
| 2026-10-24 | Nombre provisional actualizado a **Bene PDF**: paquete `bene`, comando `bene` y referencias del proyecto. Paso 1 completado: modelos de dominio, errores tipados y puerto `PdfEngine` con su DTO. 50 pruebas en verde. |

## 8. Notas de entorno

- El paquete y el comando se llaman `bene`. El bloque de estructura de `docs/requirements.md` todavía usa `pdf-studio-local`/`pdf_studio` porque es el documento original del usuario; este plan y el código usan `bene`.
- El repositorio usa identidad git local `Crise <crise@localhost>`; cámbiala con `git config user.name` / `git config user.email` si vas a publicarlo.
- Windows: `py -3.12 -m venv .venv`, luego `python -m pip install -e ".[dev]"`.
- Las comprobaciones se lanzan desde WSL llamando al Python de Windows: `.venv/Scripts/python.exe`.
- Tamaño del entorno completo: 992 MB (PySide6 653 MB, PyMuPDF 105 MB y sus extras 99 MB). El `.exe` final será mucho menor.
