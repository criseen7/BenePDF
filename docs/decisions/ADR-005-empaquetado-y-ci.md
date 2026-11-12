# ADR-005 — Empaquetado con PyInstaller y verificación en CI

- **Estado:** aceptada
- **Fecha:** 2026-11-08

## Contexto

El proyecto ya es un MVP utilizable, pero hasta la iteración 4 solo se podía
ejecutar desde el entorno virtual con `bene` o `python -m bene`. RNF-016 pide un
ejecutable instalable y RNF-017 pide pruebas automatizadas en integración
continua. Además hay que garantizar que el ejecutable incluye los recursos que
la aplicación necesita en tiempo de ejecución:

- los binarios nativos de MuPDF que usa `pymupdf`;
- los plugins y bibliotecas de Qt que usa PySide6;
- las fuentes Liberation y su licencia OFL, declaradas como `package-data`.

El proyecto se publica como código fuente bajo AGPL-3.0-only y no publica
binarios. El empaquetado de esta iteración se conserva como verificación de CI,
no como una release (ADR-001 y ADR-008). Los avisos de las dependencias se
documentan en `THIRD_PARTY_NOTICES.md`.

## Decisión

### PyInstaller en modo carpeta

Se empaqueta con **PyInstaller 6** en modo `--onedir` por defecto. El comando se
construye en `scripts/build_app.py` y se puede revisar sin ejecutarlo:

```powershell
.venv\Scripts\python.exe scripts\build_app.py --dry-run
.venv\Scripts\python.exe scripts\build_app.py
```

El resultado queda en `dist/BenePDF/BenePDF.exe`. Se ofrece `--onefile` como
opción, pero no es el modo recomendado: un único archivo tarda más en arrancar
porque se descomprime en cada ejecución y dificulta el diagnóstico de recursos
que falten.

Decisiones concretas del comando:

| Opción | Motivo |
|---|---|
| `--windowed` | La aplicación es de escritorio; no debe abrir una consola |
| `--name BenePDF` | Nombre estable del ejecutable y de la carpeta |
| `--add-data .../fonts;bene/assets/fonts` | Conserva la ruta que espera `bundled_font_path` |
| `--collect-all pymupdf` | Incluye submódulos, datos y binarios nativos de MuPDF |
| `--noconfirm --clean` | Build reproducible sin preguntas ni caché anterior |

PyInstaller se instala con el extra `build`:

```powershell
python -m pip install -e ".[build]"
```

No se añade como dependencia de ejecución: quien use el código fuente no lo
necesita.

### Verificación del paquete

La construcción se comprueba en dos niveles:

1. **Pruebas unitarias** del comando, del modo `--dry-run`, de la ruta de salida
   y de los errores accionables cuando falta PyInstaller o el directorio de
   fuentes.
2. **Build real en CI**: tras construir, el flujo comprueba que existe
   `LiberationSans-Regular.ttf` dentro de `_internal` y ejecuta
   `BenePDF.exe --version` esperando código de salida 0.

En la máquina de desarrollo se verificó además que el ejecutable imprime
`Bene PDF 0.1.0` y que las tres fuentes y los binarios de `pymupdf` están dentro
de `dist/BenePDF/_internal`.

### Integración continua

`.github/workflows/ci.yml` define tres trabajos:

| Trabajo | Plataforma | Contenido |
|---|---|---|
| `calidad` | Windows y Ubuntu | `ruff check`, `ruff format --check`, `mypy`, `pytest` offscreen y cobertura en Windows |
| `lento` | Windows | `pytest -m slow` con documentos de 100 páginas |
| `empaquetado` | Windows | build con PyInstaller y comprobación del `.exe`; no se publica el artefacto |

Las pruebas de interfaz se ejecutan con `QT_QPA_PLATFORM=offscreen`, igual que
en local. En Ubuntu se instalan las bibliotecas de sistema que necesitan los
wheels de PySide6 (`libegl1`, `libgl1`, `libxkbcommon-x11-0`, `libdbus-1-3` y
`libxcb-cursor0`).

## Consecuencias

- El ejecutable es autocontenido: no requiere Python ni el entorno virtual en la
  máquina de destino.
- El tamaño del artefacto es considerable porque incluye Qt y MuPDF. Es el
  precio de no depender de una instalación previa.
- `--onefile` queda como alternativa, no como opción por defecto.
- Las pruebas lentas no frenan la suite normal: `pyproject.toml` excluye el
  marcador `slow` y CI las ejecuta en un trabajo aparte.
- La verificación automática no sustituye a probar el ejecutable en una máquina
  Windows limpia. Esa comprobación manual sigue pendiente antes de cerrar una
  versión estable.
- El repositorio distribuye solo código fuente. El trabajo de empaquetado
  construye el ejecutable y comprueba que arranca, pero no lo sube como
  artefacto ni lo publica en Releases. Si en el futuro se distribuyera un
  binario, habría que incluir `LICENSE` y `THIRD_PARTY_NOTICES.md`, ofrecer el
  código fuente correspondiente y cumplir las obligaciones de la AGPL y de la
  LGPL de Qt/PySide6.
