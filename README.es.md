# Bene PDF

[English](README.md) | **Español**

Aplicación de escritorio para visualizar, organizar y editar documentos PDF sin subir nada a servicios externos.

El proyecto está en fase de construcción. Las iteraciones 1 a 3 cubren la apertura, la visualización, la navegación, el zoom, la rotación de vista, las miniaturas, la edición en memoria de texto e imágenes, la redacción permanente y la exportación segura a un archivo nuevo. La iteración 4 corrige el redimensionado y la exportación en páginas rotadas o recortadas, embebe las fuentes y avisa del texto que no cabe. La iteración 5 añade errores de exportación accionables, accesibilidad por teclado, pruebas con documentos de 100 páginas, empaquetado con PyInstaller e integración continua. La iteración 6 añade búsqueda de texto, información del documento, rotación/reordenación/eliminación/extracción de páginas y reemplazo de imágenes incrustadas. La iteración 7 añade dibujo libre con color y grosor configurables, con trazos vectoriales que se pueden seleccionar y redimensionar. La revisión de integridad de la hoja de ruta elimina además las anotaciones y los campos de formulario que intersectan una redacción, y añade el zoom con `Ctrl`+rueda y el aviso de cambios sin exportar en el título de la ventana.

- Requisitos y criterios de aceptación: [docs/requirements.md](docs/requirements.md)
- Hoja de ruta principal: [BenePDF_Plan_Mejoras_Evolucion_Correcciones.md](BenePDF_Plan_Mejoras_Evolucion_Correcciones.md)
- Plan de trabajo, estado y bitácora de iteraciones: [PLAN.md](PLAN.md)
- Decisiones de arquitectura: [docs/decisions/](docs/decisions/)
- Cambios por versión: [CHANGELOG.md](CHANGELOG.md)

## Requisitos

- Windows 10/11 (desarrollo y ejecución) con Python 3.12
- Sin conexión a Internet para usar la aplicación

## Instalación en Windows

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Si PowerShell bloquea la activación del entorno:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

## Guía de uso

### Abrir un PDF

1. Activa el entorno e inicia la aplicación con `bene`.
2. Pulsa **Abrir…** en la barra de herramientas o usa `Ctrl+O`.
3. También puedes arrastrar un archivo PDF desde el Explorador y soltarlo sobre la ventana.
4. Desde la terminal puedes abrir un documento directamente:

   ```powershell
   bene "C:\ruta\al\documento.pdf"
   ```

Al abrirlo, Bene PDF muestra la primera página ajustada a la ventana. Si el PDF está cifrado, pedirá la contraseña; se permiten hasta tres intentos y la contraseña solo se mantiene en memoria.

### Navegar por el documento

- Escribe el número de página en el selector de la barra superior y pulsa `Enter`.
- Usa los botones **◀** y **▶**, o las teclas `PgUp` y `PgDn`, para ir a la página anterior o siguiente.
- Haz clic en una miniatura del panel **Páginas** para saltar directamente a esa página. Las miniaturas se generan en segundo plano y la página actual queda resaltada.
- La barra de estado indica la página actual, el total, la clasificación orientativa de la página (texto, imagen escaneada, contenido gráfico o página vacía), sus dimensiones en puntos y el zoom aplicado.

Los renders se hacen en segundo plano: mientras se prepara una página verás **Renderizando…** y, al terminar, **Listo**. Las páginas ya visitadas se conservan en memoria para que volver atrás sea inmediato.

### Buscar texto

1. Pulsa **Buscar…** (`Ctrl+F`) o usa Editar → Buscar…
2. Escribe el texto y pulsa `Enter` o **Buscar**. La búsqueda recorre todo el documento en segundo plano.
3. Las coincidencias aparecen en el panel **Buscar** con su página y un fragmento. Al seleccionar una, el visor salta a su página y la resalta.
4. Usa **Siguiente** y **Anterior**, o `F3` y `Shift+F3`, para recorrer las coincidencias.

La búsqueda no distingue mayúsculas de minúsculas y no incluye OCR: en documentos escaneados sin texto reconocible no habrá resultados. Si una coincidencia está en una página eliminada de la copia de trabajo, se conserva en la lista pero se avisa de que no se exportará.

### Páginas

Las operaciones de página se aplican a la copia de trabajo y solo cambian el archivo al exportar. El selector de página y la barra de estado usan el orden de salida; si has eliminado páginas, la barra indica también el número de página original.

- **Rotar página 90°** (`Ctrl+Alt+R`): acumula una rotación adicional a la página visible. Es distinta de **Rotar vista**: la rotación de página sí se guarda en el archivo exportado.
- **Mover página arriba / abajo** (`Ctrl+Alt+↑` / `Ctrl+Alt+↓`): cambia el orden de salida.
- **Eliminar página…** (`Ctrl+Alt+Supr`): pide confirmación y avisa si la página tiene objetos añadidos, que se omitirán en la exportación. Puedes deshacerlo antes de exportar.
- **Extraer páginas…** (`Ctrl+Alt+E`): escribe una selección como `1-3, 5` en un archivo nuevo. No altera la sesión, el historial ni el estado «sin exportar».

### Reemplazar una imagen incrustada

1. Abre **Página → Reemplazar imagen…**.
2. Elige una de las imágenes detectadas en la página visible y pulsa **Elegir imagen de reemplazo…** para seleccionar un PNG o JPEG.
3. Confirma con **Reemplazar**. La sustitución se aplica solo al exportar.

Si la imagen se comparte entre varias páginas, el diálogo avisa de que cambiará en todas ellas. Las imágenes en línea, las que están dentro de formularios o las que el PDF no identifica con un `xref` fiable no se pueden reemplazar y se omiten en la lista.

### Información del documento

**Archivo → Información del documento…** (`Ctrl+Alt+I`) muestra el nombre y la ruta, el número de páginas, las páginas que se exportarán, el tamaño del archivo, las dimensiones de la página actual, la protección y los metadatos disponibles (título, autor, fechas, etc.). Los datos proceden del propio PDF y pueden faltar o ser incorrectos.

### Editar el documento

Los cambios se guardan **solo en memoria** durante la sesión: el PDF original nunca se modifica. Cuando termines, expórtalos a un archivo nuevo.

1. **Seleccionar región** (`Ctrl+Shift+R`): arrastra sobre la página para marcar un rectángulo. La barra de estado muestra sus coordenadas y tamaño en puntos PDF.
2. **Redactar región** (`Ctrl+Shift+X`): arrastra sobre el contenido que quieras eliminar. Se pide confirmación porque, al exportar, el contenido subyacente se borra de forma permanente del archivo nuevo. La región se muestra en negro y se puede mover, redimensionar o eliminar como cualquier otro objeto antes de exportar.
3. **Añadir texto** (`Ctrl+T`): escribe el contenido y elige fuente, tamaño, color y alineación. Si hay una región seleccionada, el texto ocupa esa región; si no, la herramienta queda activa y el texto se coloca con un clic. Puedes redactar una zona y escribir el texto corregido encima en el mismo paso. Las fuentes Helvetica, Times-Roman y Courier se embeben en el PDF, así que conservan el euro, los acentos y los alfabetos latinos; si el texto no cabe en su región o usa caracteres que la fuente no admite, el objeto se marca en rojo y la exportación se bloquea con un aviso que indica la página y el espacio que falta.
4. **Insertar imagen** (`Ctrl+I`): admite PNG y JPEG de hasta 20 MB. Igual que el texto, usa la región seleccionada o el siguiente clic. La imagen se ajusta a la proporción original.
5. **Dibujar** (`Ctrl+Shift+D`): arrastra sobre la página para dibujar a mano alzada. La barra **Dibujo** permite elegir el color y el grosor, de 0,5 a 50 pt. La herramienta permanece activa después de cada trazo para dibujar varios seguidos; cambia a **Seleccionar** u otra herramienta para salir. Los trazos se guardan como vectores y se pueden seleccionar, mover, redimensionar, eliminar, deshacer y rehacer como cualquier otro objeto. Al redimensionar cambia la forma, pero no el grosor. Dibujar sobre texto solo lo tapa visualmente: usa **Redactar región** para eliminar el contenido subyacente de forma permanente.
6. **Mover y redimensionar**: con la herramienta **Seleccionar** (`Ctrl+Shift+V`), haz clic en un objeto para seleccionarlo. Con el objeto seleccionado, arrastra desde su cuerpo para moverlo o desde las asas de las esquinas para cambiar su tamaño; el cursor cambia al acercarte a cada zona. Las imágenes se estiran libremente; mantén pulsada **Shift** mientras arrastras un asa para conservar su proporción. El panel **Propiedades** permite introducir X, Y, ancho y alto en puntos PDF.
7. **Eliminar** (`Supr`): borra el objeto seleccionado.
8. **Deshacer / Rehacer** (`Ctrl+Z` / `Ctrl+Y`): recorre el historial completo de la sesión, incluidas las redacciones, los trazos y las operaciones de página.

La barra de estado muestra **Cambios sin exportar** cuando hay ediciones activas, y el título de la ventana se marca con `*`. Al cerrar el documento, abrir otro PDF o salir, la aplicación ofrece **Guardar**, **Descartar** o **Cancelar**.

### Exportar el resultado

1. Pulsa **Exportar como…** (`Ctrl+Shift+S`) o usa Archivo → Exportar como…
2. Elige un nombre y una carpeta distintos del PDF original. La aplicación rechaza guardar sobre el original y propone `nombre-editado.pdf`, `nombre-editado-2.pdf`, … para no pisar una exportación anterior.
3. Si hay redacciones, confirma que se aplicarán de forma permanente.
4. Bene PDF aplica las redacciones, inserta el texto, las imágenes y los trazos nuevos, añade la rotación de página y, por último, reordena y elimina las páginas según la copia de trabajo.
5. Bene PDF escribe primero en un archivo temporal, lo reabre para validarlo y solo entonces reemplaza el destino. Si algo falla, el archivo original y el destino anterior quedan intactos; el aviso de error lo indica de forma explícita.

El archivo exportado puede abrirse de nuevo y contiene el texto, las imágenes, los trazos, las redacciones, los reemplazos de imagen y la disposición de páginas aplicadas. La redacción elimina el texto subyacente (no solo lo tapa); en páginas escaneadas borra únicamente los píxeles de la región marcada, y elimina las anotaciones y los campos de formulario cuya área intersecta la redacción. Los metadatos del documento y los archivos adjuntos incrustados quedan fuera de la región de redacción y no se sanean.

Para guardar solo algunas páginas, usa **Página → Extraer páginas…**; la extracción crea un archivo nuevo y no cambia la sesión de trabajo.

Los PDF cifrados no se pueden exportar en esta iteración: PyMuPDF necesitaría la contraseña de propietario para conservar la protección y la aplicación no la solicita ni la guarda. La acción **Exportar como…** aparece deshabilitada para esos documentos.

### Zoom y ajuste

- **Acercar** / **Alejar**: botones de la barra, `Ctrl++` / `Ctrl+-` o `Ctrl`+rueda del ratón sobre la página.
- **100 %**: `Ctrl+0`.
- **Ajustar ancho**: `Ctrl+1`.
- **Ajustar página**: `Ctrl+2`.
- El zoom manual va del 10 % al 800 %.
- Al redimensionar la ventana, los modos de ajuste recalculan la escala automáticamente.
- En pantallas HiDPI el render se genera a la densidad real para mantener la nitidez; en zooms muy altos la densidad se limita automáticamente para no agotar la memoria.

### Rotar la vista

Pulsa **Rotar vista 90°** o `Ctrl+R` para girar la página en pantalla 90° en sentido horario. Puedes repetirlo para llegar a 180° y 270°. La rotación es solo de visualización: **no modifica el PDF** y se restablece al abrir otro documento.

### Cerrar y salir

- **Cerrar documento** (`Ctrl+W`) cierra el PDF actual y deja la aplicación abierta.
- **Salir** (`Ctrl+Q`, o Archivo → Salir) cierra la aplicación.
- Abrir otro PDF cierra automáticamente el documento anterior.

### Atajos de teclado

| Acción | Atajo |
|---|---|
| Abrir PDF | `Ctrl+O` |
| Página anterior | `PgUp` |
| Página siguiente | `PgDn` |
| Acercar | `Ctrl++` |
| Alejar | `Ctrl+-` |
| Zoom 100 % | `Ctrl+0` |
| Ajustar ancho | `Ctrl+1` |
| Ajustar página | `Ctrl+2` |
| Rotar vista 90° | `Ctrl+R` |
| Herramienta seleccionar | `Ctrl+Shift+V` |
| Seleccionar región | `Ctrl+Shift+R` |
| Redactar región | `Ctrl+Shift+X` |
| Añadir texto | `Ctrl+T` |
| Insertar imagen | `Ctrl+I` |
| Dibujar | `Ctrl+Shift+D` |
| Buscar | `Ctrl+F` |
| Buscar siguiente | `F3` |
| Buscar anterior | `Shift+F3` |
| Información del documento | `Ctrl+Alt+I` |
| Rotar página 90° | `Ctrl+Alt+R` |
| Mover página arriba | `Ctrl+Alt+↑` |
| Mover página abajo | `Ctrl+Alt+↓` |
| Eliminar página | `Ctrl+Alt+Supr` |
| Extraer páginas | `Ctrl+Alt+E` |
| Exportar como… | `Ctrl+Shift+S` |
| Deshacer | `Ctrl+Z` |
| Rehacer | `Ctrl+Y` |
| Eliminar objeto | `Supr` |
| Cerrar documento | `Ctrl+W` |
| Salir | `Ctrl+Q` |

### Errores y registro

Si el archivo no existe, está dañado, no es un PDF o no se puede leer, la aplicación muestra un diálogo con el motivo. Los detalles técnicos se escriben en el registro:

- Windows: `%LOCALAPPDATA%\bene-pdf\logs\bene.log`
- Linux: `$XDG_STATE_HOME/bene-pdf/logs/bene.log` o `~/.local/state/bene-pdf/logs/bene.log`

El registro rota a 2 MB, conserva tres copias y nunca contiene el texto del documento.

### Accesibilidad y teclado

- Todos los controles principales tienen nombre y descripción accesibles: ventana, lienzo, navegación, selector de página, miniaturas, diálogo de texto, barra de dibujo y panel de propiedades.
- Las etiquetas del formulario están asociadas a su campo y el recorrido con `Tab` sigue un orden lógico: navegación → miniaturas → lienzo, y texto → fuente → tamaño → color → alineación en el diálogo.
- Cada miniatura anuncia «Página N» y su tooltip indica a qué página lleva.
- El lienzo tiene foco explícito y actualiza su descripción con la página, el tipo y las dimensiones.

La comprobación automática cubre nombres, etiquetas y orden de tabulación. Antes de una versión distribuible conviene revisarla con un lector de pantalla real (Narrador en Windows u Orca en Linux).

### Documentos grandes

La suite incluye pruebas con PDFs sintéticos de **100 páginas de texto** y **100 páginas escaneadas**. Comprueban la apertura, la clasificación de la primera y la última página y el render de ambos extremos. Están marcadas como `slow` y no se ejecutan en la suite rápida:

```powershell
pytest -m slow
```

### Empaquetar un ejecutable

El ejecutable se construye con PyInstaller y el extra `build`:

```powershell
python -m pip install -e ".[dev,build]"
python scripts/build_app.py
```

El resultado queda en `dist\BenePDF\BenePDF.exe`. El comando incluye las fuentes Liberation, los binarios de MuPDF y los plugins de Qt. Para revisar el comando sin construirlo:

```powershell
python scripts/build_app.py --dry-run
```

También se puede generar un único archivo con `--onefile`, aunque tarda más en arrancar. El ejecutable no necesita Python instalado en la máquina de destino.

### Integración continua

`.github/workflows/ci.yml` ejecuta en cada push y pull request:

- **Windows y Ubuntu:** `ruff check`, `ruff format --check`, `mypy` y `pytest` con `QT_QPA_PLATFORM=offscreen`.
- **Windows:** cobertura, pruebas lentas (`pytest -m slow`) y construcción del ejecutable.
- El artefacto `BenePDF-windows` se publica al final del trabajo de empaquetado.

### Limitaciones de esta iteración

- Los cambios de edición viven en memoria hasta que se exportan; el PDF original nunca se modifica.
- Los PDF cifrados no se pueden exportar mientras conserven la protección.
- No hay OCR ni impresión; la búsqueda solo encuentra texto reconocible, no escaneos.
- Las miniaturas reflejan el orden y la rotación adicional de las páginas, pero se generan a partir del PDF original: el texto, las imágenes y las redacciones añadidas no aparecen en ellas.
- La rotación de vista no se guarda en el archivo; la rotación de página sí se aplica al exportar.
- El reemplazo de imagen no está disponible para imágenes en línea, dentro de formularios o sin un `xref` fiable.
- El dibujo solo admite trazos a mano alzada: todavía no hay líneas rectas, flechas, formas ni resaltador, y no se captura la presión ni la inclinación del lápiz.
- Un trazo es contenido vectorial nuevo; tapa el texto, pero no lo elimina. Para borrarlo de forma permanente hay que usar la redacción.
- El grosor de un trazo queda fijado al crearlo; redimensionarlo cambia su forma, no el ancho de línea.
- La redacción puede afectar a objetos que se solapen con la región marcada; revísala antes de exportar.
- La redacción elimina el contenido, las anotaciones y los campos de formulario que intersectan la región, pero no limpia los metadatos del documento ni los archivos adjuntos incrustados.
- Si una página concreta no se puede renderizar, se muestra un aviso y el detalle queda en el registro.
- La interfaz se ha verificado en modo offscreen sobre Windows (y en CI sobre Ubuntu); falta una revisión visual con pantalla real, DPI y lector de pantalla antes de una versión distribuible.
- Linux se prueba en CI en modo offscreen, pero no se ha validado visualmente.
- El ejecutable incluye Qt y MuPDF, así que ocupa cientos de MB. Es el coste de no exigir Python en la máquina de destino.
- La comprobación del ejecutable en CI se limita a `--version` y a la presencia de recursos; abrir, editar y exportar en una máquina Windows limpia sigue siendo una prueba manual pendiente.

## Comandos

```powershell
bene                    # abre la aplicación
bene documento.pdf      # abre un PDF al iniciar
pytest                  # pruebas rápidas
pytest -m slow          # documentos grandes y rendimiento
pytest -m ui            # solo interfaz
ruff check .            # lint
ruff format .           # formato
mypy                    # tipado estático
python scripts/verify_env.py      # comprueba Python, PyMuPDF y Qt
python scripts/benchmark_open.py  # mide el criterio de rendimiento RNF-001
python scripts/build_app.py       # construye dist/BenePDF
python scripts/build_app.py --dry-run  # muestra el comando de PyInstaller
```

Para ejecutar la interfaz en un entorno sin pantalla (CI):

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
pytest -m ui
```

## Estructura

```text
src/bene/
├── main.py           # punto de entrada
├── bootstrap.py      # composición de dependencias
├── domain/           # modelos, reglas y errores
├── application/      # puertos y casos de uso
├── infrastructure/   # adaptadores (PyMuPDF, almacenamiento, logs)
└── presentation/     # ventana Qt, visor y workers
```

La interfaz no importa PyMuPDF: solo conoce los puertos de la capa de aplicación. Hay una prueba que verifica esa frontera.

## Licencias

El proyecto es de uso personal y no se distribuye. Usa PyMuPDF bajo su licencia AGPL-3.0, lo que impide distribuir la aplicación sin cumplir esa licencia. Ver [ADR-001](docs/decisions/ADR-001-motor-pdf.md).
