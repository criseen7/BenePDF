# PLAN — Bene PDF

- **Estado:** iteración 1 implementada y verificada en modo offscreen
- **Última actualización:** 2026-10-24
- **Especificación de referencia:** [docs/requirements.md](docs/requirements.md)

## 1. Decisiones adoptadas

| Tema | Decisión | Motivo |
|---|---|---|
| Nombre | **Bene PDF** (provisional) | Elegido por el usuario; paquete Python `bene`, comando `bene` |
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

- [x] `infrastructure/pdf/pymupdf_engine.py`, único módulo que importa `pymupdf`
- [x] Render RGB888 con matriz de escala
- [x] Contraseña en memoria para PDF cifrados; detección de texto/escaneado
- [x] Traducción de errores de MuPDF a errores de dominio

Detalles verificados contra la API real de PyMuPDF 2.0:

- `page.rect` ya incluye `/Rotate`, así que `PageInfo` guarda las dimensiones sin rotación y la rotación aparte; `rotated_size` da el tamaño visible.
- `authenticate()` funciona aunque `needs_pass` siga activo, y `is_encrypted` pasa a `False` tras autenticar: el indicador se captura **antes** de autenticar.
- PyMuPDF abre `.txt`, imágenes y EPUB como documentos no-PDF; el adaptador rechaza todo lo que no tenga `is_pdf`.
- Cada sesión usa un `threading.Lock`: PyMuPDF no es seguro entre hilos y el visor pedirá renders desde un hilo de trabajo.
- Límite de 40 MP por render, comprobado antes de reservar memoria.

### Paso 3 — Casos de uso

- [x] `open_document.py`: validación de ruta, extensión y tamaño máximo
- [x] `render_page.py`: validación de índice y zoom

`OpenDocument` valida existencia, tipo de entrada y tamaño (512 MB por defecto) y
delega en el motor; `RenderPage` valida índice, rotación de vista, escala
(0,1–8) y el límite de píxeles. Los porcentajes de zoom y los mensajes quedan
fuera de la interfaz, que solo traducirá errores a texto comprensible.

Resultado medido con `scripts/benchmark_open.py` (100 páginas de texto, 0,58 MB):

| Medida | Tiempo |
|---|---|
| Apertura | 0,8 ms |
| Info de la página 1 | 8,1 ms |
| Render al 100 % | 3,9 ms |
| Primera página visible | **0,01 s** (objetivo ≤ 3 s) |

### Paso 4 — Presentación

- [x] `main_window.py`: barra superior, visor y barra de estado
- [x] `viewer/pdf_canvas.py`: widget que pinta el `QImage`
- [x] Render en `QThreadPool` con descarte de resultados obsoletos
- [x] Caché LRU acotada por número de páginas y memoria
- [x] Abrir desde diálogo y arrastrando archivos; contraseña para PDF cifrados

La ventana abre en **ajustar página**, con barra de herramientas, menús Archivo/Ver/Ayuda y barra de estado con título, página, clasificación, dimensiones y zoom. Al redimensionar se recalcula el ajuste con un retardo de 150 ms para no lanzar renders intermedios.

El planificador de render mantiene **un render en curso y como máximo uno pendiente**: cada petición lleva un token y solo se entrega el resultado de la última. Los renders de páginas que ya no están visibles se guardan igualmente en la caché, de modo que volver atrás es inmediato. La caché LRU se limita a 24 entradas y 128 MB, conservando siempre la más reciente.

La contraseña se pide en un diálogo modal y se mantiene solo en memoria; se permiten tres intentos antes de mostrar el error. Los PDF se pueden abrir con el diálogo, por línea de comandos o arrastrándolos a la ventana. Los errores previstos se muestran con su mensaje en español y los inesperados remiten al registro técnico.

### Paso 5 — Infraestructura transversal

- [x] `bootstrap.py` como composition root
- [x] Logging rotativo en `%LOCALAPPDATA%\bene-pdf\logs`, sin texto del documento
- [x] Rutas de configuración con la biblioteca estándar en lugar de `QStandardPaths`

`bootstrap.create_application()` construye el motor, los casos de uso y la ventana en un solo lugar; `main.py` solo interpreta argumentos, crea la `QApplication` y ejecuta el bucle de eventos.

El registro usa `RotatingFileHandler` (2 MB por archivo, 3 copias) y nunca recibe el contenido del documento. Las rutas se calculan sin Qt: `LOCALAPPDATA` en Windows y `XDG_DATA_HOME`/`XDG_STATE_HOME` en Linux. Así el arranque, el registro y sus pruebas funcionan sin crear una aplicación gráfica.

### Paso 6 — Pruebas

- [x] Unitarias con `FakePdfEngine`: validaciones y casos de uso
- [x] Integración contra PDFs sintéticos generados en el test
- [x] Smoke test de UI con `QT_QPA_PLATFORM=offscreen`
- [x] Test de frontera: `pymupdf` solo en `infrastructure/pdf`; `PySide6` solo en `presentation` y `main.py`
- [x] Benchmark manual con PDF de 100 páginas (< 3 s la primera página)

Resultado: **225 pruebas en verde** (44 de interfaz), `ruff` y `mypy` sin errores en 51 archivos. La prueba de frontera analiza los imports con `ast` y comprueba además que dominio y aplicación no dependan de capas exteriores.

Además del smoke test automático, se ejecutó la aplicación real en modo offscreen con PyMuPDF: abrir un PDF de 5 páginas, navegar cinco páginas, cambiar a zoom 200 %, ajustar al ancho y rotar la vista, con renders agrupados y sin bloqueos. El registro se creó y no contenía el texto del documento.

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
| 2026-10-24 | Pasos 2 y 3 completados: adaptador PyMuPDF (apertura, cifrado, clasificación, render con cerrojo) y casos de uso de apertura y render. 71 pruebas nuevas, 121 en total. Benchmark de 100 páginas: primera página visible en 0,01 s. |
| 2026-10-24 | Pasos 4, 5 y 6 completados: ventana PySide6, visor, planificador de render con descarte de resultados obsoletos, caché LRU, zoom/ajuste/rotación, apertura por diálogo y arrastre, contraseña, errores en diálogos, bootstrap, registro rotativo y rutas sin Qt. 104 pruebas nuevas (44 de interfaz), 225 en total. Smoke test real offscreen con PyMuPDF y navegación/zoom/rotación. |

## 8. Notas de entorno

- El paquete y el comando se llaman `bene`. El bloque de estructura de `docs/requirements.md` todavía usa `pdf-studio-local`/`pdf_studio` porque es el documento original del usuario; este plan y el código usan `bene`.
- **Desviación del plan original:** las rutas se calculan con la biblioteca estándar (`LOCALAPPDATA` en Windows; `XDG_DATA_HOME`/`XDG_STATE_HOME` en Linux) y no con `QStandardPaths`. Motivo: mantener `config.py`, el registro y `bootstrap.py` libres de Qt, de modo que se puedan probar sin `QApplication` y que el arranque no dependa de la inicialización gráfica. En Windows la ubicación es la misma que daría Qt: `%LOCALAPPDATA%\bene-pdf`.
- El registro técnico está en `%LOCALAPPDATA%\bene-pdf\logs\bene.log` (Windows) o `$XDG_STATE_HOME/bene-pdf/logs/bene.log` (Linux). Rota a 2 MB y conserva 3 copias.
- El repositorio usa identidad git local `Crise <crise@localhost>`; cámbiala con `git config user.name` / `git config user.email` si vas a publicarlo.
- Windows: `py -3.12 -m venv .venv`, luego `python -m pip install -e ".[dev]"`.
- Las comprobaciones se lanzan desde WSL llamando al Python de Windows: `.venv/Scripts/python.exe`.
- Tamaño del entorno completo: 992 MB (PySide6 653 MB, PyMuPDF 105 MB y sus extras 99 MB). El `.exe` final será mucho menor.
