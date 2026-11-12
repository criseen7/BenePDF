# Avisos de terceros

BenePDF se distribuye como código fuente bajo la GNU Affero General Public
License v3.0 only (`AGPL-3.0-only`). Este documento resume las licencias de las
dependencias y los recursos de terceros. No sustituye a los textos completos de
cada licencia.

## Dependencias de ejecución

| Componente | Versión | Licencia | Enlaces |
|---|---|---|---|
| PyMuPDF | `>=2.0,<3` | AGPL-3.0 o licencia comercial de Artifex | [Repositorio](https://github.com/pymupdf/PyMuPDF), [AGPL-3.0](https://www.gnu.org/licenses/agpl-3.0.html), [Licencia comercial](https://artifex.com/licensing/) |
| MuPDF | Incluido en PyMuPDF | AGPL-3.0 o licencia comercial de Artifex | [Sitio oficial](https://mupdf.com/), [Licencias](https://mupdf.com/licensing/) |
| PySide6 | `>=6.12,<6.13` | LGPL-3.0-only, GPL-2.0-only o GPL-3.0-only | [Licencias de Qt for Python](https://doc.qt.io/qtforpython-6/licenses.html), [LGPL-3.0](https://www.gnu.org/licenses/lgpl-3.0.html) |
| shiboken6 | `6.12` | LGPL-3.0-only, GPL-2.0-only o GPL-3.0-only | [Licencias de Qt for Python](https://doc.qt.io/qtforpython-6/licenses.html), [LGPL-3.0](https://www.gnu.org/licenses/lgpl-3.0.html) |
| Qt | `6.12` | LGPL-3.0-only o licencia comercial | [Licencias de Qt](https://www.qt.io/licensing) |
| Fuentes Liberation | Incluidas en `src/bene/assets/fonts` | SIL Open Font License 1.1 | [`OFL.txt`](src/bene/assets/fonts/OFL.txt), [SIL OFL](https://scripts.sil.org/OFL) |
| Python | `>=3.12,<3.14` | Python Software Foundation License 2.0 | [Licencia de Python](https://docs.python.org/3/license.html) |

BenePDF usa PyMuPDF bajo la opción **AGPL-3.0**, licencia su propio código como
**AGPL-3.0-only** y usa PySide6/Qt bajo la opción **LGPL-3.0**. No se usa la
licencia comercial de Artifex ni la licencia comercial de Qt.

## Dependencias transitivas

PyMuPDF instala dependencias adicionales para sus funciones opcionales
(`networkx`, `numpy`, `onnxruntime`, `PyYAML`, `pymupdf-layout`, `pymupdf4llm`,
`psutil` y `tabulate`). No forman parte del código fuente de BenePDF: `pip` las
descarga desde PyPI y conservan sus propias licencias. Si en el futuro se
publica un ejecutable, habrá que revisar las licencias de las dependencias que
PyInstaller incluya realmente en el paquete.

## Distribución solo de código fuente

Este repositorio no publica ejecutables ni artefactos binarios. El flujo de
integración continua construye el ejecutable únicamente para comprobar que el
empaquetado funciona y lo descarta al terminar; no lo sube como artefacto ni lo
publica en Releases.

Si en el futuro se distribuyen binarios, será necesario:

- incluir `LICENSE`, este archivo y los textos de licencia aplicables;
- ofrecer el código fuente correspondiente a la versión distribuida;
- cumplir las obligaciones de la LGPL para Qt/PySide6, incluyendo la posibilidad
  de sustituir las bibliotecas compartidas;
- revisar de nuevo las licencias de todas las dependencias empaquetadas.
