# Bene PDF

Aplicación de escritorio para visualizar, organizar y editar documentos PDF sin subir nada a servicios externos.

El proyecto está en fase de construcción: la iteración 1 cubre apertura, visualización, navegación, zoom, rotación de vista y detección de páginas escaneadas. La iteración 2 añade miniaturas, selección de región, texto e imágenes, transformaciones y deshacer/rehacer, todo en memoria. La exportación y la redacción permanente llegan en la iteración 3.

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

Los cambios se guardan **solo en memoria** durante la sesión: el PDF original nunca se modifica. La exportación llegará en la iteración 3.

1. **Seleccionar región** (`Ctrl+Shift+R`): arrastra sobre la página para marcar un rectángulo. La barra de estado muestra sus coordenadas y tamaño en puntos PDF.
2. **Añadir texto** (`Ctrl+T`): escribe el contenido y elige fuente, tamaño, color y alineación. Si hay una región seleccionada, el texto ocupa esa región; si no, la herramienta queda activa y el texto se coloca con un clic.
3. **Insertar imagen** (`Ctrl+I`): admite PNG y JPEG de hasta 20 MB. Igual que el texto, usa la región seleccionada o el siguiente clic. La imagen se ajusta a la proporción original.
4. **Mover y redimensionar**: con la herramienta **Seleccionar** (`Ctrl+Shift+V`), haz clic en un objeto para seleccionarlo, arrástralo para moverlo o usa las asas de las esquinas para cambiar su tamaño. También puedes empezar a redimensionar con un clic directo en el asa, sin seleccionar antes; el cursor cambia al acercarte a una esquina. El panel **Propiedades** permite introducir X, Y, ancho y alto en puntos PDF.
5. **Eliminar** (`Supr`): borra el objeto seleccionado.
6. **Deshacer / Rehacer** (`Ctrl+Z` / `Ctrl+Y`): recorre el historial completo de la sesión.

La barra de estado muestra **Cambios sin exportar** cuando hay ediciones activas. Al cerrar el documento, abrir otro PDF o salir, la aplicación pide confirmación antes de descartarlas.

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
| Añadir texto | `Ctrl+T` |
| Insertar imagen | `Ctrl+I` |
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

- Los cambios de edición viven solo en memoria: todavía no se pueden exportar ni guardar. El PDF original nunca se modifica.
- No hay redacción permanente, búsqueda, OCR ni impresión; llegan en la iteración 3 o más adelante.
- Las miniaturas y los renders se generan a partir del PDF original, así que las ediciones no aparecen en ellas.
- La rotación de vista no se guarda en el archivo.
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
