# PLAN — Bene PDF

- **Estado:** iteraciones 1 a 7 implementadas; correcciones P0/P1 de la hoja de ruta aplicadas; licenciamiento público AGPL-3.0-only definido; pendiente la revisión visual en Windows
- **Última actualización:** 2026-11-12
- **Hoja de ruta principal:** [BenePDF_Plan_Mejoras_Evolucion_Correcciones.md](BenePDF_Plan_Mejoras_Evolucion_Correcciones.md)
- **Especificación de referencia:** [docs/requirements.md](docs/requirements.md)

## 1. Decisiones adoptadas

| Tema | Decisión | Motivo |
|---|---|---|
| Nombre | **Bene PDF** (provisional) | Elegido por el usuario; paquete Python `bene`, comando `bene` |
| Distribución | Repositorio público solo de código fuente; sin binarios en Releases | PyMuPDF exige AGPL o licencia comercial; publicar solo el código evita distribuir binarios y sus obligaciones adicionales |
| Licencia | `AGPL-3.0-only`, titular `criseen7` | Es compatible con PyMuPDF y deja explícitos los términos de reutilización (ADR-008) |
| Lenguaje | Python 3.12 (Windows nativo) | Es la versión instalada en la máquina objetivo y la que soportan todas las ruedas |
| Interfaz | PySide6 6.12, textos en español | Qt cubre visor, diálogos y tareas en segundo plano; licencia LGPL |
| Motor PDF | PyMuPDF 2.0 (`pymupdf`) tras el puerto `PdfEngine` | Render, inserción de texto e imágenes y redacción real con una sola dependencia |
| Modelo de edición | Comandos inmutables en memoria; el PDF fuente nunca se modifica | Deshacer/rehacer correcto y cumplimiento de RN-001 y RN-008 |
| Persistencia | Nada se guarda hasta exportar; la exportación escribe a temporal y valida | Integridad del archivo original (RNF-005) |
| Redacción | Se aplica antes que el contenido nuevo; texto, vectores, anotaciones y campos que intersectan se eliminan, las imágenes se redactan por píxeles | Permite «redactar y escribir encima» sin destruir escaneos completos y evita que queden datos sensibles en anotaciones o formularios (RN-004, RNF-008) |
| Hoja de ruta | `BenePDF_Plan_Mejoras_Evolucion_Correcciones.md` es la referencia de prioridades; `PLAN.md` registra la ejecución | Separa el plan estratégico del historial de iteraciones y evita duplicar decisiones |
| Dibujo libre | Trazos vectoriales con puntos en coordenadas visibles y grosor en puntos PDF | Se seleccionan y transforman como el resto de objetos y no pierden calidad al ampliar (RF-026, ADR-007) |
| Empaquetado | PyInstaller 6 en modo carpeta (`--onedir`), solo para verificar el build | Incluye Qt, MuPDF y fuentes sin exigir Python en destino; el repositorio no publica el ejecutable (RNF-016) |
| CI | GitHub Actions en Windows y Ubuntu, pruebas lentas aparte; el trabajo de empaquetado no sube el `.exe` | Detecta regresiones de plataforma, mantiene la suite rápida y respeta la distribución solo de código (RNF-017) |
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

## 3. Iteración 2 — edición en memoria

**Objetivo verificable:** seleccionar regiones, añadir texto e imágenes, moverlas y redimensionarlas, deshacer y rehacer, con miniaturas de página y sin modificar el PDF original.

### Paso 1 — Modelo de edición e historial

- [x] `domain/editing.py`: `TextStyle`, `TextObject`, `ImageObject` y comandos inmutables
- [x] `apply_command`: estado nuevo a partir del anterior, sin mutaciones
- [x] `EditHistory`: índice de comandos activos, deshacer/rehacer y descarte del futuro
- [x] `EditSession`: altas, transformaciones, eliminación, consultas y estado sucio
- [x] Errores tipados de objeto inexistente y operación inválida
- [x] Pruebas unitarias de modelos, comandos, historial y sesión

### Paso 2 — Coordenadas y lienzo

- [x] `CoordinateMapper` para pantalla ↔ puntos PDF con zoom y rotación de vista
- [x] Selección rectangular de región con conversión correcta a puntos PDF
- [x] Dibujo de objetos, selección, asas de redimensionado y arrastre
- [x] Pruebas unitarias de las cuatro rotaciones y de la ida y vuelta

### Paso 3 — Texto e imágenes

- [x] Diálogo de texto: contenido, fuente, tamaño, color y alineación
- [x] Colocación de texto en una región o con un clic
- [x] Inserción de PNG/JPEG desde archivo, con límite de tamaño
- [x] Vista previa de texto e imágenes con `QPainter`
- [x] Eliminación de objetos añadidos

### Paso 4 — Historial y propiedades en la interfaz

- [x] Acciones Deshacer/Rehacer con atajos y estado habilitado
- [x] Panel de propiedades con posición y tamaño numéricos
- [x] Indicador de cambios sin exportar y aviso al cerrar o abrir otro documento
- [x] Sincronización entre selección del lienzo y panel de propiedades

### Paso 5 — Miniaturas

- [x] Carga asíncrona y secuencial de miniaturas con tamaño acotado
- [x] Panel lateral con página actual resaltada y navegación por clic
- [x] Cancelación y liberación al cerrar o cambiar de documento

### Paso 6 — Verificación

- [x] Pruebas unitarias, de integración y de interfaz en verde
- [x] `ruff` y `mypy` sin errores
- [x] Smoke real offscreen con PyMuPDF: miniaturas, texto, imagen y deshacer
- [x] README y bitácora actualizados

## 4. Iteración 3 — redacción y exportación segura

**Objetivo verificable:** marcar regiones de redacción con confirmación, exportar los cambios a un archivo nuevo sin tocar el original y comprobar por extracción de texto que el contenido redactado ya no existe.

### Paso 1 — Modelo y sesión

- [x] `RedactionObject` y `AddRedactionCommand` en el modelo inmutable
- [x] `EditSession.add_redaction` y reutilización de mover/redimensionar/eliminar
- [x] Estado limpio comparando la tupla de comandos activos, no solo su cantidad
- [x] Pruebas de redacciones, deshacer/rehacer y `mark_saved`

### Paso 2 — Lienzo y propiedades

- [x] `CanvasTool.REDACT` con arrastre y señal `redaction_requested`
- [x] Vista previa de la región en negro con borde discontinuo
- [x] Selección, asas, movimiento y eliminación de redacciones como cualquier objeto
- [x] Panel de propiedades con título y aviso de eliminación permanente

### Paso 3 — Exportación

- [x] `ExportError`, `OpenedDocument.export_to` y caso de uso `ExportDocument`
- [x] Rechazo del destino igual al original en el caso de uso y en el adaptador
- [x] Copia limpia del original, archivo temporal en el mismo directorio y `Path.replace()`
- [x] Redacciones antes que textos e imágenes; contenido nuevo encima de la zona redactada
- [x] Conversión de coordenadas visibles a sin rotar y orientación correcta en las cuatro rotaciones
- [x] Redacción de imágenes por píxeles para conservar el resto del escaneo
- [x] Validación reabriendo el temporal: PDF, número de páginas y ausencia de anotaciones de redacción
- [x] Rechazo explícito de PDF cifrados, sin guardar contraseñas

### Paso 4 — Interfaz

- [x] Acción **Redactar región** (`Ctrl+Shift+X`) y confirmación al marcar
- [x] Acción **Exportar como…** (`Ctrl+Shift+S`) y confirmación al aplicar redacciones
- [x] Aviso **Guardar / Descartar / Cancelar** al cerrar, abrir otro documento o salir
- [x] Estado limpio tras exportar y acción deshabilitada para PDF cifrados
- [x] Resumen de la exportación en la barra de estado

### Paso 5 — Verificación

- [x] Pruebas unitarias de dominio, sesión y caso de uso
- [x] Pruebas de integración con PyMuPDF: no extracción, rotaciones, escaneos, imágenes y temporales
- [x] Pruebas de interfaz y smoke real con redacción y exportación
- [x] `ruff` y `mypy` sin errores
- [x] README, PLAN y ADR-003 actualizados

## 5. Iteración 4 — corrección de los bugs de edición y exportación

**Objetivo verificable:** que redimensionar texto e imágenes se refleje en tiempo real y que el PDF exportado reproduzca exactamente lo que muestra la vista previa, incluidas las páginas rotadas y con CropBox desplazado.

### Decisiones de producto

- **Fuente abierta embebida** (Liberation Sans/Serif/Mono) para que la vista previa y la exportación compartan métricas y cubran `€`, acentos, griego y cirílico.
- **Imágenes:** estirar libre al redimensionar; **Shift** conserva la proporción.
- **Texto que no cabe:** bloquear la exportación con un aviso que indique página, objeto y espacio que falta.

### Paso 0 — Pruebas de regresión (en rojo)

- [x] Texto multi-línea en 0/90/180/270 × izquierda/centro/derecha: orden, alineación y región
- [x] Imagen con CropBox desplazado × rotación: posición y orientación
- [x] Las asas del lienzo siguen al preview durante el arrastre
- [x] **Shift** conserva la proporción al redimensionar
- [x] `€` y acentos se conservan en el PDF exportado
- [x] El aviso de texto que no cabe identifica el objeto
- [x] Un fallo de exportación no modifica un destino existente
- [x] El nombre por defecto no pisa una exportación anterior

Las pruebas se escribieron primero y se confirmaron 9 fallos esperados antes de
tocar la implementación.

### Paso 1 — Asas durante el redimensionado

- [x] `_paint_selection` y el hit-test usan `_display_rect`
- [x] Prueba de render durante el arrastre
- [x] **Shift** conserva la proporción; sin Shift la imagen se estira

### Paso 2 — Rotación del texto

- [x] `_insert_text` usa `rotate=page.rotation`
- [x] ADR-003 actualizado

### Paso 3 — Fuente embebida

- [x] TTFs de Liberation y licencia OFL en `src/bene/assets/fonts`
- [x] `package-data` en `pyproject.toml`
- [x] `infrastructure/fonts.py` con mapa, resolución y alias
- [x] `presentation/fonts.py` registra la misma familia en Qt
- [x] `_insert_text` y `_paint_text` usan la misma fuente
- [x] *Fallback* a Base-14 si falta el recurso

### Paso 4 — Overflow accionable

- [x] `measure_text` en el puerto y el adaptador
- [x] Detección de glifos no soportados
- [x] Indicador de overflow en el lienzo
- [x] Mensaje con página, objeto y déficit

### Paso 5 — Exportación y destino

- [x] Nombre por defecto sin colisiones (`-editado-2.pdf`, …)
- [x] Aviso explícito de que el destino existente no se modificó
- [x] No marcar la sesión como limpia si falla

### Paso 6 — Imagen con CropBox + rotación

- [x] Transformación visible→página con la matriz validada
- [x] Pruebas de las combinaciones CropBox × rotación

### Paso 7 — Cierre

- [x] ADR de fuentes y requisitos actualizados
- [x] `pytest`, `ruff` y `mypy` en verde
- [x] Smoke real con PDF rotado y recortado

### Criterios de verificación de la iteración 4

1. Los tiradores siguen al cursor durante todo el arrastre.
2. El texto multi-línea se exporta en 0/90/180/270 con la posición, el orden y la alineación del preview.
3. Lo que el preview marca como «cabe» se exporta; si no cabe, se avisa antes y no se genera un archivo engañoso.
4. `€`, acentos, griego y cirílico se conservan; emoji y CJK se reportan como no soportados.
5. Las imágenes se colocan correctamente con CropBox desplazado y `/Rotate`.
6. **Shift** conserva la proporción; sin Shift la imagen se estira.
7. Un fallo de exportación nunca deja un destino que parezca actualizado.
8. `pytest`, `ruff` y `mypy` en verde.

## 6. Iteración 5 — calidad, accesibilidad, PDFs grandes y distribución

**Objetivo verificable:** que la aplicación se pueda construir como ejecutable,
que los errores del sistema de archivos sean accionables, que la interfaz se
pueda recorrer con el teclado y que un documento de 100 páginas se abra y
renderice sin problemas. Todo con integración continua en Windows y Ubuntu.

### Paso 1 — Errores de exportación accionables

- [x] Pruebas en rojo para `PermissionError` y disco lleno al crear el temporal
- [x] Pruebas en rojo para fallos al reemplazar el destino
- [x] Mensaje con la carpeta, el error del sistema y qué comprobar
- [x] El destino anterior nunca se modifica y el temporal se elimina
- [x] Exportación correcta a rutas Unicode con espacios

### Paso 2 — Accesibilidad

- [x] Nombres y descripciones accesibles en la ventana y el lienzo
- [x] Nombres en navegación, selector de página y miniaturas
- [x] Etiqueta **Texto** asociada al editor con `setBuddy`
- [x] Nombres accesibles en fuente, tamaño, color y alineación
- [x] Nombres accesibles en coordenadas, tamaño y botón de aplicar
- [x] Orden de tabulación explícito en navegación, diálogo y propiedades
- [x] Cada miniatura anuncia «Página N» y su tooltip
- [x] El lienzo mantiene `StrongFocus` y actualiza su descripción con la página

### Paso 3 — Documentos grandes

- [x] PDF sintético de 100 páginas de texto: apertura, clasificación y render de los extremos
- [x] PDF sintético de 100 páginas escaneadas: apertura, clasificación y render de los extremos
- [x] Marcador `slow` y exclusión de la suite rápida
- [x] CI ejecuta `pytest -m slow` en un trabajo aparte

### Paso 4 — Empaquetado

- [x] Extra `build` con PyInstaller
- [x] `scripts/build_app.py` con `--onedir`, `--onefile` y `--dry-run`
- [x] Inclusión de las fuentes Liberation con `--add-data`
- [x] Inclusión de MuPDF con `--collect-all pymupdf`
- [x] Pruebas del comando, la ruta de salida y los errores accionables
- [x] Build real verificado: `dist/BenePDF/BenePDF.exe --version`
- [x] Comprobado que las fuentes y `pymupdf` están dentro de `_internal`

### Paso 5 — Integración continua

- [x] `.github/workflows/ci.yml` para Windows y Ubuntu
- [x] `ruff check`, `ruff format --check`, `mypy` y `pytest` offscreen
- [x] Cobertura publicada como artefacto
- [x] Trabajo de pruebas lentas
- [x] Trabajo de empaquetado con comprobación del `.exe`; el artefacto descargable se retiró al adoptar la distribución solo de código (ADR-008)

### Paso 6 — Cierre documental

- [x] ADR-005 de empaquetado y CI
- [x] README con accesibilidad, documentos grandes, build y CI
- [x] PLAN actualizado con la iteración 5 y la bitácora
- [x] `pytest`, `ruff` y `mypy` en verde

### Criterios de verificación de la iteración 5

1. Un fallo de permisos o de espacio al exportar muestra un mensaje que indica
   la carpeta y qué comprobar; el destino anterior queda intacto.
2. Los controles principales tienen nombre accesible y el recorrido con Tab
   sigue un orden lógico en la ventana, el diálogo de texto y las propiedades.
3. Los documentos de 100 páginas, de texto y escaneados, se abren, clasifican y
   renderizan sin agotar memoria.
4. `python scripts/build_app.py` genera un ejecutable que arranca y contiene las
   fuentes y los binarios de MuPDF.
5. CI ejecuta lint, formato, tipado, pruebas y build en Windows y Ubuntu.
6. La suite rápida sigue en verde y las pruebas lentas se ejecutan aparte.
7. `pytest`, `ruff` y `mypy` en verde.

## 7. Iteración 6 — búsqueda, información, páginas y reemplazo de imagen

**Objetivo verificable:** localizar texto y navegar a sus coincidencias, consultar
metadatos y tamaño del archivo, reordenar/rotar/eliminar/extraer páginas y
sustituir una imagen incrustada, todo sin modificar el PDF original y con
deshacer/rehacer compartido con las ediciones de objetos.

### Paso 1 — Información del documento (RF-022)

- [x] Diálogo con metadatos, tamaño del archivo, páginas y protección
- [x] Tamaño de la página actual y páginas que se exportarán
- [x] Acción en el menú **Archivo** y atajo `Ctrl+Alt+I`

### Paso 2 — Búsqueda de texto (RF-020)

- [x] Búsqueda en segundo plano con token para descartar resultados obsoletos
- [x] Panel con lista de coincidencias, recuento y navegación anterior/siguiente
- [x] Resaltado de coincidencias en el lienzo y selección automática de la primera
- [x] Aviso cuando una coincidencia está en una página eliminada de la copia
- [x] Sin OCR: los documentos escaneados no devuelven texto

### Paso 3 — Páginas (RF-021, RF-023)

- [x] `PageArrangement` con índices fuente estables, orden de salida y rotación adicional
- [x] Comandos `RotatePageCommand`, `MovePageCommand` y `DeletePageCommand` en el historial
- [x] Rotar, mover y eliminar la página visible; eliminar pide confirmación
- [x] Extraer una selección a un archivo nuevo sin alterar la sesión ni marcarla como guardada
- [x] Exportación: ediciones → rotación adicional → `document.select(order)`
- [x] Miniaturas, render y caché indexados por página fuente y rotación total

### Paso 4 — Reemplazo de imagen (RF-013)

- [x] Detección de imágenes con `xref` reemplazable
- [x] `ImageReplacementObject` y `AddImageReplacementCommand`
- [x] Diálogo con vista previa y aviso de imágenes compartidas entre páginas
- [x] Reemplazo con `Page.replace_image` solo al exportar
- [x] Las imágenes en línea o sin `xref` se omiten con una explicación

### Paso 5 — Cierre

- [x] Pruebas unitarias, de integración y de interfaz
- [x] ADR-006 de disposición de páginas, búsqueda y reemplazo de imagen
- [x] README y PLAN actualizados
- [x] `pytest`, `ruff` y `mypy` en verde

### Criterios de verificación de la iteración 6

1. La búsqueda localiza texto, muestra las coincidencias y navega a su página;
   una búsqueda nueva descarta los resultados de la anterior.
2. El diálogo de información muestra páginas, tamaño, dimensiones y los
   metadatos disponibles sin modificar el documento.
3. Reordenar, rotar o eliminar páginas se refleja en la copia exportada; el PDF
   original no cambia y deshacer/rehacer restaura la disposición anterior.
4. Eliminar una página avisa de los objetos añadidos que se omitirán.
5. Extraer páginas genera un archivo nuevo con la selección y no altera el
   historial ni el estado «sin exportar» de la sesión.
6. Reemplazar una imagen incrustada se aplica solo al exportar; si la imagen es
   compartida, el diálogo avisa de que cambiará en todas sus páginas.
7. `pytest`, `ruff` y `mypy` en verde, con la suite rápida y las pruebas lentas.

## 8. Iteración 7 — dibujo libre

**Objetivo verificable:** dibujar trazos a mano alzada con color y grosor
configurables, seleccionarlos y transformarlos como cualquier otro objeto,
deshacerlos y exportarlos como vectores sin modificar el PDF original.

### Paso 1 — Modelo y sesión (RF-026)

- [x] `StrokeStyle` con color `#rrggbb`, grosor en puntos y validación
- [x] `StrokeObject` con puntos en coordenadas visibles y `rect` calculado con el grosor
- [x] `AddStrokeCommand` en el historial compartido
- [x] Mover desplaza los puntos; redimensionar los escala y conserva el grosor
- [x] `EditSession.add_stroke` con identificadores `trazo-N`

### Paso 2 — Exportación vectorial

- [x] Conversión de cada punto visible al espacio sin rotar de la página
- [x] `draw_polyline` con extremos y uniones redondeados
- [x] Punto aislado con `draw_circle` relleno y sin borde duplicado
- [x] Trazos después de redacciones y antes de la rotación adicional y `document.select`
- [x] `stroke_count` en `ExportResult` y en el resumen de exportación
- [x] Los trazos de páginas eliminadas no se exportan

### Paso 3 — Lienzo e interfaz

- [x] `CanvasTool.DRAW` con vista previa, captura y deduplicación de puntos
- [x] La herramienta permanece activa después de cada trazo
- [x] Acción **Dibujar** (`Ctrl+Shift+D`) y barra **Dibujo**
- [x] Grosor de `0.5` a `50` pt y selector de color
- [x] Panel de propiedades con tipo, color, grosor y número de puntos
- [x] El diálogo de texto recuerda el último estilo aceptado

### Paso 4 — Cierre

- [x] Pruebas unitarias, de integración y de interfaz
- [x] ADR-007 de dibujo libre
- [x] README, README.es.md y PLAN actualizados
- [x] `pytest`, `ruff` y `mypy` en verde, incluida la suite lenta

### Criterios de verificación de la iteración 7

1. Dibujar con el ratón crea un trazo con el color y el grosor elegidos y la
   herramienta sigue activa para el siguiente trazo.
2. El trazo se puede seleccionar, mover, redimensionar, eliminar y
   deshacer/rehacer; al redimensionar cambia la forma pero no el grosor.
3. Un clic sin arrastre crea un punto visible y seleccionable.
4. La exportación dibuja los trazos como vectores sobre la página correcta,
   respeta `/Rotate`, CropBox y la rotación adicional, y no modifica el original.
5. Los trazos de páginas eliminadas no aparecen en el archivo exportado.
6. El resumen y el registro de exportación cuentan los trazos.
7. `pytest`, `ruff` y `mypy` en verde, con la suite rápida y las pruebas lentas.

### Revisión de integridad y UX de la hoja de ruta (2026-11-10)

Se revisó `BenePDF_Plan_Mejoras_Evolucion_Correcciones.md` contra el código y se
aplicaron solo las correcciones P0/P1 de bajo riesgo:

- [x] La redacción elimina las anotaciones y los campos de formulario que
      intersectan la región; los de fuera se conservan.
- [x] Documento sintético con texto, anotaciones y campos dentro y fuera de la
      zona, y pruebas de extracción y renderizado.
- [x] Pruebas de redacción parcial de texto y de eliminación de vectores.
- [x] Zoom con `Ctrl`+rueda sobre el lienzo, con señal `zoom_requested`.
- [x] El título de la ventana marca los cambios sin exportar con `*`.
- [x] ADR-003, README bilingüe, AGENTS y CHANGELOG actualizados.
- [x] Se documenta que la redacción por región no sanea metadatos ni adjuntos.
- [ ] Revisión visual en Windows y prueba del ejecutable en una máquina limpia.

## 9. Estructura objetivo

```text
EditorPDF-Local/
├── PLAN.md
├── README.md                 # guía principal en inglés
├── README.es.md              # guía en español
├── BenePDF_Plan_Mejoras_Evolucion_Correcciones.md  # hoja de ruta principal
├── CHANGELOG.md
├── pyproject.toml
├── .github/
│   └── workflows/
│       └── ci.yml            # calidad, pruebas lentas y empaquetado
├── docs/
│   ├── requirements.md
│   └── decisions/
│       ├── ADR-001-motor-pdf.md
│       ├── ADR-002-modelo-de-edicion.md
│       ├── ADR-003-exportacion-y-redaccion.md
│       ├── ADR-004-fuentes-embebidas.md
│       ├── ADR-005-empaquetado-y-ci.md
│       ├── ADR-006-paginas-busqueda-y-reemplazo.md
│       └── ADR-007-dibujo-libre.md
├── scripts/
│   ├── build_app.py          # PyInstaller con fuentes y MuPDF
│   ├── benchmark_open.py
│   └── verify_env.py
├── src/bene/
│   ├── main.py
│   ├── bootstrap.py
│   ├── config.py
│   ├── assets/
│   │   └── fonts/            # Liberation Sans/Serif/Mono + OFL.txt
│   ├── domain/
│   ├── application/
│   │   ├── ports/
│   │   └── use_cases/
│   ├── infrastructure/
│   │   ├── fonts.py          # mapa de fuentes y resolución de los TTF
│   │   ├── pdf/
│   │   └── logging/
│   └── presentation/
│       ├── main_window.py
│       ├── fonts.py          # registro de las mismas familias en Qt
│       ├── viewer/
│       └── workers/
└── tests/
    ├── unit/
    ├── integration/
    ├── ui/
    └── fixtures/
```

## 10. Criterios de verificación de la iteración 1

1. `pytest` en verde en Windows (unitarias, integración y UI offscreen).
2. `ruff check` y `ruff format --check` sin errores.
3. `mypy` sin errores en dominio, aplicación e infraestructura.
4. PDF real de 100 páginas: primera página en menos de 3 s y navegación sin bloqueos.
5. PDF corrupto, cifrado y escaneado: mensajes claros y sin cierre inesperado.
6. El log existe, rota y no contiene texto del documento.

## 11. Criterios de verificación de la iteración 2

1. Las cuatro rotaciones de vista convierten pantalla ↔ PDF sin desfases y la ida y vuelta conserva el punto.
2. Se puede añadir, mover, redimensionar y eliminar texto e imágenes con la vista previa actualizada.
3. Deshacer y rehacer reconstruyen exactamente el estado anterior, incluidos los objetos eliminados.
4. Las miniaturas se cargan sin bloquear la interfaz y navegan a la página correcta.
5. El PDF original no se modifica y no se escribe ningún archivo.
6. `pytest`, `ruff` y `mypy` en verde y smoke real offscreen correcto.

## 12. Criterios de verificación de la iteración 3

1. El texto de una región redactada no se puede extraer del archivo exportado.
2. El PDF original conserva exactamente sus bytes y nunca se sobrescribe.
3. La exportación escribe a un temporal, lo valida y no deja restos si falla.
4. Las redacciones y los elementos nuevos se colocan correctamente en páginas con `/Rotate`.
5. Se puede redactar y escribir texto nuevo en la misma región.
6. En un escaneo, la redacción elimina solo la región y conserva el resto de la imagen.
7. Los PDF cifrados se rechazan de forma explícita y no se degrada su protección.
8. `pytest`, `ruff` y `mypy` en verde y smoke real offscreen correcto.

## 13. Riesgos abiertos

| Riesgo | Impacto | Mitigación |
|---|---|---|
| PyMuPDF 2.0 es muy reciente | Alto | Versión fijada `>=2.0,<3`; probado con 2.0 y 2.1; las constantes se leen por nombre para tolerar cambios en las anotaciones; plan B: `1.28.2` con el parche de redacción |
| La vista previa por capas no reproduce el resultado exacto | Medio | Botón de vista previa exacta aplicando comandos a una copia en memoria |
| Redacción puede eliminar objetos solapados | Alto | Vista previa con la zona marcada, confirmación explícita y pruebas con objetos cercanos |
| Rendimiento en PDF escaneados de gran tamaño | Medio | Render bajo demanda, caché acotada y tareas en segundo plano; prueba de 100 páginas marcada `slow` |
| El ejecutable incluye Qt y MuPDF y ocupa cientos de MB | Medio | Modo carpeta; el tamaño es el precio de no exigir Python en destino |
| El build depende de hooks de PyInstaller para PySide6/PyMuPDF | Medio | `--collect-all pymupdf`, comprobación de fuentes y `--version` en CI |
| La accesibilidad automática no equivale a un lector de pantalla | Medio | Nombres, etiquetas y orden de tabulación probados; falta revisión manual con Narrador/Orca |
| Linux no se ha probado visualmente | Bajo | CI ejecuta pruebas offscreen en Ubuntu con las bibliotecas de Qt |
| La búsqueda no incluye OCR | Bajo | Se documenta; los escaneos no devuelven texto hasta una iteración futura con OCR |
| Reemplazar una imagen compartida cambia todas sus apariciones | Medio | El diálogo muestra las páginas afectadas antes de aceptar |
| Algunas imágenes no se pueden reemplazar (en línea, formularios, sin `xref`) | Bajo | Se omiten en la detección y el diálogo explica la limitación |
| Un trazo con muchísimos puntos engorda el PDF y ralentiza la vista previa | Bajo | El lienzo descarta muestras muy próximas; el trazo se guarda como vector, no como imagen |
| El grosor no cambia al redimensionar un trazo | Bajo | Es una decisión de ADR-007; para engrosarlo se dibuja de nuevo o se ajusta el estilo antes |
| Dibujar no sustituye a la redacción | Medio | La interfaz y la documentación recuerdan que un trazo tapa pero no elimina el texto subyacente (RN-009) |
| La redacción por región no limpia metadatos ni adjuntos | Medio | Se documenta la limitación; un saneamiento completo requiere una acción explícita sobre el documento |

## 14. Backlog posterior

| Iteración | Contenido |
|---|---|
| 2 | Miniaturas, selección de región, conversión de coordenadas, añadir texto e imágenes, mover/redimensionar, historial deshacer/rehacer |
| 3 | **Completada:** redacción permanente con confirmación, exportación atómica a un archivo nuevo y pruebas de no extracción |
| 4 | **Completada:** corrección del redimensionado y de la exportación en páginas rotadas/recortadas, fuentes embebidas y avisos de overflow |
| 5 | **Completada:** errores de exportación accionables, accesibilidad, PDFs de 100 páginas, PyInstaller, CI en Windows/Ubuntu y ADR-005 |
| 6 | **Completada:** búsqueda de texto, información del documento, operaciones de páginas (rotar, reordenar, eliminar, extraer) y reemplazo de imagen |
| 7 | **Completada:** dibujo libre con trazos vectoriales, color y grosor, transformación, historial y exportación (ADR-007) |
| Hoja de ruta | **P0 aplicado:** redacción de anotaciones y campos; **P1 aplicado:** `Ctrl`+rueda y marca de cambios en el título. Pendientes: OCR local opcional, líneas/formas/flechas, resaltador, comparación antes/después, procesamiento por lotes y firmas |
| 8 | OCR local opcional, líneas/formas/flechas, resaltador y comparación antes/después |

## 15. Bitácora

| Fecha | Avance |
|---|---|
| 2026-10-24 | Análisis de requisitos y plan acordado. Paso 0 ejecutado: proyecto, herramientas, docs y entorno verificado. |
| 2026-10-24 | Nombre provisional actualizado a **Bene PDF**: paquete `bene`, comando `bene` y referencias del proyecto. Paso 1 completado: modelos de dominio, errores tipados y puerto `PdfEngine` con su DTO. 50 pruebas en verde. |
| 2026-10-24 | Pasos 2 y 3 completados: adaptador PyMuPDF (apertura, cifrado, clasificación, render con cerrojo) y casos de uso de apertura y render. 71 pruebas nuevas, 121 en total. Benchmark de 100 páginas: primera página visible en 0,01 s. |
| 2026-10-24 | Pasos 4, 5 y 6 completados: ventana PySide6, visor, planificador de render con descarte de resultados obsoletos, caché LRU, zoom/ajuste/rotación, apertura por diálogo y arrastre, contraseña, errores en diálogos, bootstrap, registro rotativo y rutas sin Qt. 104 pruebas nuevas (44 de interfaz), 225 en total. Smoke test real offscreen con PyMuPDF y navegación/zoom/rotación. |
| 2026-10-25 | Iteración 2 iniciada. Paso 1 completado: modelos de edición, comandos inmutables, aplicación de comandos, historial y sesión con deshacer/rehacer. 31 pruebas nuevas. |
| 2026-10-25 | Paso 2 completado: `CoordinateMapper` con zoom y las cuatro rotaciones, selección de región, dibujo de texto e imágenes, selección y transformación por arrastre en el lienzo. 47 pruebas nuevas, 303 en total. |
| 2026-10-25 | Paso 5 completado: cargador secuencial de miniaturas en segundo plano, panel lateral navegable y cancelación al cerrar. 13 pruebas nuevas, 316 en total. |
| 2026-10-25 | Pasos 3, 4 y 6 completados: diálogo de texto, panel de propiedades, carga validada de PNG/JPEG, integración de todas las acciones de edición en la ventana principal, deshacer/rehacer, aviso de cambios sin exportar y smoke real con PyMuPDF. 34 pruebas nuevas, 350 en total. El render se repite si la escala cambia mientras está en curso para no quedarse en «Renderizando…». |
| 2026-10-26 | Correcciones de la iteración 2: el render usa la densidad de la pantalla (HiDPI) y reduce la densidad si el zoom agotaría el límite de memoria; el redimensionado funciona al arrastrar las asas visibles y muestra cursores adecuados; la acción «Rotar vista 90°» vuelve a girar la página. 7 pruebas nuevas, 358 en total. |
| 2026-10-26 | Ajuste del redimensionado: solo las asas visibles del objeto seleccionado cambian su tamaño; arrastrar el cuerpo siempre mueve, incluso cerca de una esquina. 1 prueba nueva, 359 en total. |
| 2026-10-26 | Iteración 3, pasos 1 y 2: `RedactionObject` y `AddRedactionCommand`, estado limpio por tupla de comandos, herramienta **Redactar región**, vista previa en negro y panel de propiedades. Pruebas de dominio, sesión, lienzo y panel. |
| 2026-10-26 | Iteración 3, paso 3: `ExportError`, `export_to`, caso de uso `ExportDocument`, copia limpia, temporal validado y reemplazo atómico. Redacciones antes del contenido nuevo, coordenadas rotadas y rechazo explícito de PDF cifrados. Pruebas de integración de no extracción, rotaciones, escaneos, imágenes y temporales. |
| 2026-10-26 | Iteración 3, pasos 4 y 5: acciones Exportar/Redactar, confirmaciones al marcar y al exportar, aviso Guardar/Descartar/Cancelar y estado limpio. Smoke real con redacción y exportación. README, PLAN y ADR-003 actualizados. 403 pruebas en verde. |
| 2026-11-07 | Iteración 4 iniciada: plan de corrección del redimensionado y de la exportación. Diagnóstico confirmado (asas desfasadas, `rotate` invertido, métricas Qt/PyMuPDF, `€` no soportado, destino obsoleto y CropBox+rotación). Paso 0: pruebas de regresión con 9 fallos esperados. |
| 2026-11-07 | Iteración 4 completada. Asas e hit-test sobre el preview, **Shift** conserva la proporción y sin Shift la imagen se estira; `rotate=page.rotation`; fuentes Liberation embebidas con *fallback* a Base-14; `measure_text` y aviso de overflow; nombre de exportación sin colisiones y aviso de destino intacto; transformación visible→página con CropBox y `/Rotate` para texto, imagen y redacción. ADR-004, requisitos y README actualizados. 437 pruebas en verde, `ruff` y `mypy` sin errores. |
| 2026-11-08 | Iteración 5 completada. Errores de exportación accionables para permisos, disco lleno y fallo de reemplazo, con el destino intacto; nombres accesibles, etiquetas asociadas y orden de tabulación en ventana, diálogo, propiedades y miniaturas; pruebas de 100 páginas de texto y escaneadas marcadas `slow`; `scripts/build_app.py` y extra `build`; CI para Windows y Ubuntu con trabajos de calidad, lentas y empaquetado; ADR-005, README y PLAN actualizados. Ejecutable `dist/BenePDF/BenePDF.exe` construido y verificado con `--version`. |
| 2026-11-10 | Iteración 6 completada. Búsqueda de texto en segundo plano con resaltado y navegación; diálogo de información con metadatos, tamaño y páginas de salida; `PageArrangement` con índices fuente estables y comandos de rotar, mover y eliminar páginas en el historial; extracción de una selección sin alterar la sesión; reemplazo de imágenes incrustadas con aviso de imágenes compartidas; exportación con orden, eliminación y rotación adicional; ADR-006, README y PLAN actualizados. Revisión de la iteración 5/6: se corrigió la validación de rango en objetos, se hizo inmutable `PageArrangement.rotations`, su igualdad incluye la rotación y el resumen de exportación ya no cuenta objetos de páginas eliminadas. 562 pruebas rápidas y 2 lentas en verde, `ruff` y `mypy` limpios. |
| 2026-11-10 | Corregido el CI de Windows: PyMuPDF 2.1 declara constantes que 2.0 solo expone en tiempo de ejecución, así que los `# type: ignore` sobraban en CI y faltaban en local. Las constantes de redacción y cifrado se leen con un auxiliar `getattr` que funciona con ambas versiones. Verificado con PyMuPDF 2.0 y 2.1: 562 pruebas rápidas y 2 lentas en verde, `ruff` y `mypy` limpios. |
| 2026-11-10 | README bilingüe: `README.md` pasa a ser la guía principal en inglés y el contenido español se conserva en `README.es.md`, con enlaces cruzados entre ambos. Se anota que la interfaz y la documentación detallada siguen en español. |
| 2026-11-10 | Iteración 7 completada. Dibujo libre con `StrokeStyle`, `StrokeObject` y `AddStrokeCommand`; puntos en coordenadas visibles y caja calculada con el grosor; mover y redimensionar transforman los puntos y conservan el grosor; herramienta **Dibujar** (`Ctrl+Shift+D`) con vista previa, deduplicación y barra de color/grosor; panel de propiedades y memoria del último estilo de texto; exportación vectorial con `draw_polyline`/`draw_circle`, rotaciones, CropBox, redacción y páginas eliminadas; `stroke_count` en el resumen; ADR-007, requisitos y README bilingüe actualizados. 605 pruebas rápidas y 2 lentas en verde, `ruff` y `mypy` limpios. |
| 2026-11-10 | Adoptada `BenePDF_Plan_Mejoras_Evolucion_Correcciones.md` como hoja de ruta principal. Revisión de integridad: `Page.apply_redactions` no borraba anotaciones ni campos de formulario; ahora `_remove_redacted_annotations` elimina los que intersectan la región y conserva los de fuera. Pruebas nuevas con un PDF sintético de anotaciones y formularios, redacción parcial de texto y vectores. UX: zoom con `Ctrl`+rueda mediante `PdfCanvas.zoom_requested` y marca `*` en el título cuando hay cambios sin exportar. Se documenta que la redacción por región no sanea metadatos ni adjuntos. ADR-003, README bilingüe, AGENTS, PLAN y CHANGELOG actualizados. 613 pruebas rápidas y 2 lentas en verde, `ruff` y `mypy` limpios. |
| 2026-11-12 | Licenciamiento público definido: BenePDF pasa a `AGPL-3.0-only` con titular `criseen7`. Se añaden `LICENSE` y `THIRD_PARTY_NOTICES.md`, se declara la licencia en `pyproject.toml` con SPDX y se actualizan README bilingüe, ADR-001, ADR-005 y el nuevo ADR-008. El CI deja de subir `BenePDF-windows`: sigue construyendo y verificando el ejecutable, pero no lo publica. Revisión inicial del historial sin secretos reales ni binarios rastreados. |

## 16. Notas de entorno

- El paquete y el comando se llaman `bene`. El bloque de estructura de `docs/requirements.md` todavía usa `pdf-studio-local`/`pdf_studio` porque es el documento original del usuario; este plan y el código usan `bene`.
- **Desviación del plan original:** las rutas se calculan con la biblioteca estándar (`LOCALAPPDATA` en Windows; `XDG_DATA_HOME`/`XDG_STATE_HOME` en Linux) y no con `QStandardPaths`. Motivo: mantener `config.py`, el registro y `bootstrap.py` libres de Qt, de modo que se puedan probar sin `QApplication` y que el arranque no dependa de la inicialización gráfica. En Windows la ubicación es la misma que daría Qt: `%LOCALAPPDATA%\bene-pdf`.
- El registro técnico está en `%LOCALAPPDATA%\bene-pdf\logs\bene.log` (Windows) o `$XDG_STATE_HOME/bene-pdf/logs/bene.log` (Linux). Rota a 2 MB y conserva 3 copias.
- La identidad git local es `Crise <crise@localhost>`. El aviso de copyright usa el seudónimo `criseen7`; no se publica un correo real.
- Windows: `py -3.12 -m venv .venv`, luego `python -m pip install -e ".[dev]"`.
- Las comprobaciones se lanzan desde WSL llamando al Python de Windows: `.venv/Scripts/python.exe`.
- Tamaño del entorno completo: 992 MB (PySide6 653 MB, PyMuPDF 105 MB y sus extras 99 MB). Con PyInstaller instalado, el entorno crece otros ~20 MB.
- El ejecutable se construye con `python scripts/build_app.py` y queda en `dist/BenePDF/` (ignorado por git). El modo `--onefile` está disponible, pero tarda más en arrancar.
- Las pruebas lentas se ejecutan con `pytest -m slow`; la suite normal las excluye mediante `addopts`.
- CI usa `QT_QPA_PLATFORM=offscreen` y, en Ubuntu, instala las bibliotecas de sistema que necesitan los wheels de PySide6.

## 17. Publicación del repositorio

- [x] `LICENSE` con AGPL-3.0-only y copyright de `criseen7`.
- [x] `THIRD_PARTY_NOTICES.md` con las licencias de PyMuPDF/MuPDF, PySide6/Qt, las fuentes Liberation y Python.
- [x] `pyproject.toml` con licencia SPDX y archivos de licencia.
- [x] README bilingüe, ADR-001, ADR-005, ADR-008, PLAN y CHANGELOG actualizados.
- [x] El CI construye el ejecutable solo para verificarlo y no lo sube como artefacto.
- [x] Revisión inicial del historial: sin secretos reales, binarios, `.env` ni PDFs rastreados; los blobs grandes son las fuentes Liberation.
- [ ] Borrar los artefactos antiguos `BenePDF-windows` de GitHub Actions antes de hacer público el repositorio.
- [ ] Confirmar que no hay Releases ni paquetes publicados.
- [ ] Revisar la descripción y la licencia detectada por GitHub.
