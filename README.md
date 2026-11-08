# Bene PDF

Aplicación de escritorio para visualizar, organizar y editar documentos PDF sin subir nada a servicios externos.

El proyecto está en fase de construcción: la iteración 1 cubre apertura, visualización, navegación, zoom, rotación de vista y detección de páginas escaneadas. La iteración 2 añade miniaturas, selección de región, texto e imágenes, transformaciones y deshacer/rehacer, todo en memoria. La iteración 3 añade redacción permanente y exportación segura a un archivo nuevo.

- Requisitos y criterios de aceptación: [docs/requirements.md](docs/requirements.md)
- Plan de trabajo y estado: [PLAN.md](PLAN.md)
- Decisiones de arquitectura: [docs/decisions/](docs/decisions/)

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

### Editar el documento

Los cambios se guardan **solo en memoria** durante la sesión: el PDF original nunca se modifica. Cuando termines, expórtalos a un archivo nuevo.

1. **Seleccionar región** (`Ctrl+Shift+R`): arrastra sobre la página para marcar un rectángulo. La barra de estado muestra sus coordenadas y tamaño en puntos PDF.
2. **Redactar región** (`Ctrl+Shift+X`): arrastra sobre el contenido que quieras eliminar. Se pide confirmación porque, al exportar, el contenido subyacente se borra de forma permanente del archivo nuevo. La región se muestra en negro y se puede mover, redimensionar o eliminar como cualquier otro objeto antes de exportar.
3. **Añadir texto** (`Ctrl+T`): escribe el contenido y elige fuente, tamaño, color y alineación. Si hay una región seleccionada, el texto ocupa esa región; si no, la herramienta queda activa y el texto se coloca con un clic. Puedes redactar una zona y escribir el texto corregido encima en el mismo paso. Las fuentes Helvetica, Times-Roman y Courier se embeben en el PDF, así que conservan el euro, los acentos y los alfabetos latinos; si el texto no cabe en su región o usa caracteres que la fuente no admite, el objeto se marca en rojo y la exportación se bloquea con un aviso que indica la página y el espacio que falta.
4. **Insertar imagen** (`Ctrl+I`): admite PNG y JPEG de hasta 20 MB. Igual que el texto, usa la región seleccionada o el siguiente clic. La imagen se ajusta a la proporción original.
5. **Mover y redimensionar**: con la herramienta **Seleccionar** (`Ctrl+Shift+V`), haz clic en un objeto para seleccionarlo. Con el objeto seleccionado, arrastra desde su cuerpo para moverlo o desde las asas de las esquinas para cambiar su tamaño; el cursor cambia al acercarte a cada zona. Las imágenes se estiran libremente; mantén pulsada **Shift** mientras arrastras un asa para conservar su proporción. El panel **Propiedades** permite introducir X, Y, ancho y alto en puntos PDF.
6. **Eliminar** (`Supr`): borra el objeto seleccionado.
7. **Deshacer / Rehacer** (`Ctrl+Z` / `Ctrl+Y`): recorre el historial completo de la sesión, incluidas las redacciones.

La barra de estado muestra **Cambios sin exportar** cuando hay ediciones activas. Al cerrar el documento, abrir otro PDF o salir, la aplicación ofrece **Guardar**, **Descartar** o **Cancelar**.

### Exportar el resultado

1. Pulsa **Exportar como…** (`Ctrl+Shift+S`) o usa Archivo → Exportar como…
2. Elige un nombre y una carpeta distintos del PDF original. La aplicación rechaza guardar sobre el original y propone `nombre-editado.pdf`, `nombre-editado-2.pdf`, … para no pisar una exportación anterior.
3. Si hay redacciones, confirma que se aplicarán de forma permanente.
4. Bene PDF escribe primero en un archivo temporal, lo reabre para validarlo y solo entonces reemplaza el destino. Si algo falla, el archivo original y el destino anterior quedan intactos; el aviso de error lo indica de forma explícita.

El archivo exportado puede abrirse de nuevo y contiene el texto, las imágenes y las redacciones aplicadas. La redacción elimina el texto subyacente (no solo lo tapa) y, en páginas escaneadas, borra únicamente los píxeles de la región marcada.

Los PDF cifrados no se pueden exportar en esta iteración: PyMuPDF necesitaría la contraseña de propietario para conservar la protección y la aplicación no la solicita ni la guarda. La acción **Exportar como…** aparece deshabilitada para esos documentos.

### Zoom y ajuste

- **Acercar** / **Alejar**: botones de la barra o `Ctrl++` / `Ctrl+-`.
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

### Limitaciones de esta iteración

- Los cambios de edición viven en memoria hasta que se exportan; el PDF original nunca se modifica.
- Los PDF cifrados no se pueden exportar mientras conserven la protección.
- No hay búsqueda, OCR ni impresión; llegan en iteraciones posteriores.
- Las miniaturas y los renders se generan a partir del PDF original, así que las ediciones no aparecen en ellas.
- La rotación de vista no se guarda en el archivo.
- La redacción puede afectar a objetos que se solapen con la región marcada; revísala antes de exportar.
- Si una página concreta no se puede renderizar, se muestra un aviso y el detalle queda en el registro.

## Comandos

```powershell
bene                    # abre la aplicación
bene documento.pdf      # abre un PDF al iniciar
pytest                  # pruebas
ruff check .            # lint
ruff format .           # formato
mypy                    # tipado estático
python scripts/verify_env.py   # comprueba Python, PyMuPDF y Qt
python scripts/benchmark_open.py  # mide el criterio de rendimiento RNF-001
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
