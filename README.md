# Editor PDF (local)

Aplicación de escritorio para visualizar, organizar y editar documentos PDF sin subir nada a servicios externos.

El proyecto está en fase de construcción: la iteración 1 cubre apertura, visualización, navegación, zoom, rotación de vista y detección de páginas escaneadas. La edición de texto e imágenes llega en la iteración 2 y la redacción permanente en la iteración 3.

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

## Comandos

```powershell
pdf-studio              # abre la aplicación
pytest                  # pruebas
ruff check .            # lint
ruff format .           # formato
mypy                    # tipado estático
python scripts/verify_env.py   # comprueba Python, PyMuPDF y Qt
```

Para ejecutar la interfaz en un entorno sin pantalla (CI):

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
pytest -m ui
```

## Estructura

```text
src/pdf_studio/
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
