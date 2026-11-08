# PLAN — Bene PDF

- **Estado:** iteración 4 implementada y verificada en modo offscreen
- **Última actualización:** 2026-11-07
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
| Redacción | Se aplica antes que el contenido nuevo; texto y vectores se eliminan, las imágenes se redactan por píxeles | Permite «redactar y escribir encima» sin destruir escaneos completos (RN-004, RNF-008) |
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

## 6. Estructura objetivo

```text
EditorPDF-Local/
├── PLAN.md
├── README.md
├── pyproject.toml
├── docs/
│   ├── requirements.md
│   └── decisions/
│       ├── ADR-001-motor-pdf.md
│       ├── ADR-002-modelo-de-edicion.md
│       ├── ADR-003-exportacion-y-redaccion.md
│       └── ADR-004-fuentes-embebidas.md
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

## 7. Criterios de verificación de la iteración 1

1. `pytest` en verde en Windows (unitarias, integración y UI offscreen).
2. `ruff check` y `ruff format --check` sin errores.
3. `mypy` sin errores en dominio, aplicación e infraestructura.
4. PDF real de 100 páginas: primera página en menos de 3 s y navegación sin bloqueos.
5. PDF corrupto, cifrado y escaneado: mensajes claros y sin cierre inesperado.
6. El log existe, rota y no contiene texto del documento.

## 8. Criterios de verificación de la iteración 2

1. Las cuatro rotaciones de vista convierten pantalla ↔ PDF sin desfases y la ida y vuelta conserva el punto.
2. Se puede añadir, mover, redimensionar y eliminar texto e imágenes con la vista previa actualizada.
3. Deshacer y rehacer reconstruyen exactamente el estado anterior, incluidos los objetos eliminados.
4. Las miniaturas se cargan sin bloquear la interfaz y navegan a la página correcta.
5. El PDF original no se modifica y no se escribe ningún archivo.
6. `pytest`, `ruff` y `mypy` en verde y smoke real offscreen correcto.

## 9. Criterios de verificación de la iteración 3

1. El texto de una región redactada no se puede extraer del archivo exportado.
2. El PDF original conserva exactamente sus bytes y nunca se sobrescribe.
3. La exportación escribe a un temporal, lo valida y no deja restos si falla.
4. Las redacciones y los elementos nuevos se colocan correctamente en páginas con `/Rotate`.
5. Se puede redactar y escribir texto nuevo en la misma región.
6. En un escaneo, la redacción elimina solo la región y conserva el resto de la imagen.
7. Los PDF cifrados se rechazan de forma explícita y no se degrada su protección.
8. `pytest`, `ruff` y `mypy` en verde y smoke real offscreen correcto.

## 10. Riesgos abiertos

| Riesgo | Impacto | Mitigación |
|---|---|---|
| PyMuPDF 2.0 es muy reciente | Alto | Versión fijada `>=2.0,<3`; plan B: `1.28.2` con el parche de redacción |
| La vista previa por capas no reproduce el resultado exacto | Medio | Botón de vista previa exacta aplicando comandos a una copia en memoria |
| Redacción puede eliminar objetos solapados | Alto | Vista previa con la zona marcada, confirmación explícita y pruebas con objetos cercanos |
| Rendimiento en PDF escaneados de gran tamaño | Medio | Render bajo demanda, caché acotada y tareas en segundo plano |

## 11. Backlog posterior

| Iteración | Contenido |
|---|---|
| 2 | Miniaturas, selección de región, conversión de coordenadas, añadir texto e imágenes, mover/redimensionar, historial deshacer/rehacer |
| 3 | **Completada:** redacción permanente con confirmación, exportación atómica a un archivo nuevo y pruebas de no extracción |
| 4 | **Completada:** corrección del redimensionado y de la exportación en páginas rotadas/recortadas, fuentes embebidas y avisos de overflow |
| 5 | Mensajes de error, accesibilidad, PDFs grandes, empaquetado con PyInstaller |
| 6 | OCR local opcional, búsqueda, operaciones de páginas |

## 12. Bitácora

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

## 13. Notas de entorno

- El paquete y el comando se llaman `bene`. El bloque de estructura de `docs/requirements.md` todavía usa `pdf-studio-local`/`pdf_studio` porque es el documento original del usuario; este plan y el código usan `bene`.
- **Desviación del plan original:** las rutas se calculan con la biblioteca estándar (`LOCALAPPDATA` en Windows; `XDG_DATA_HOME`/`XDG_STATE_HOME` en Linux) y no con `QStandardPaths`. Motivo: mantener `config.py`, el registro y `bootstrap.py` libres de Qt, de modo que se puedan probar sin `QApplication` y que el arranque no dependa de la inicialización gráfica. En Windows la ubicación es la misma que daría Qt: `%LOCALAPPDATA%\bene-pdf`.
- El registro técnico está en `%LOCALAPPDATA%\bene-pdf\logs\bene.log` (Windows) o `$XDG_STATE_HOME/bene-pdf/logs/bene.log` (Linux). Rota a 2 MB y conserva 3 copias.
- El repositorio usa identidad git local `Crise <crise@localhost>`; cámbiala con `git config user.name` / `git config user.email` si vas a publicarlo.
- Windows: `py -3.12 -m venv .venv`, luego `python -m pip install -e ".[dev]"`.
- Las comprobaciones se lanzan desde WSL llamando al Python de Windows: `.venv/Scripts/python.exe`.
- Tamaño del entorno completo: 992 MB (PySide6 653 MB, PyMuPDF 105 MB y sus extras 99 MB). El `.exe` final será mucho menor.
