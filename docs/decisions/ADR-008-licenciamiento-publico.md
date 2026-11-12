# ADR-008 — Licenciamiento público y distribución solo de código fuente

- **Estado:** aceptada
- **Fecha:** 2026-11-12
- **Contexto del proyecto:** repositorio público, sin binarios en Releases

## Contexto

BenePDF se prepara para publicarse como repositorio público. El proyecto usa
PyMuPDF 2.x, cuya licencia es **AGPL-3.0 o comercial de Artifex**. También usa
PySide6/Qt bajo LGPL-3.0 y fuentes Liberation bajo SIL OFL 1.1.

Publicar el repositorio sin una licencia explícita dejaría el código bajo el
régimen por defecto de todos los derechos reservados, lo que impediría reutilizarlo
legalmente. Además, la licencia del motor PDF condiciona cualquier licencia que
se quiera aplicar al conjunto.

Se decide publicar **solo el código fuente**, sin ejecutables ni artefactos
binarios en Releases. El flujo de integración continua puede construir el
ejecutable para comprobar el empaquetado, pero no debe conservarlo como
artefacto descargable.

## Decisión

- BenePDF se licencia bajo **GNU Affero General Public License v3.0 only**
  (`AGPL-3.0-only`).
- El titular del copyright es **criseen7**.
- Se añade `LICENSE` con el texto completo de la AGPL-3.0 y el aviso de
  copyright.
- Se añade `THIRD_PARTY_NOTICES.md` con las licencias de PyMuPDF/MuPDF,
  PySide6/shiboken6/Qt, las fuentes Liberation y Python.
- `pyproject.toml` declara la licencia mediante la expresión SPDX
  `AGPL-3.0-only` y los archivos de licencia.
- No se publican binarios en GitHub Releases ni como artefactos del CI. El
  trabajo de empaquetado solo construye y verifica el ejecutable.
- Se usa la opción AGPL de PyMuPDF; no se adquiere la licencia comercial de
  Artifex.

## Consecuencias

- Cualquiera puede usar, estudiar, modificar y redistribuir el código bajo los
  términos de la AGPL-3.0.
- Quien distribuya una versión modificada o un binario construido a partir de
  este código debe cumplir la AGPL: ofrecer el código fuente correspondiente,
  conservar los avisos y no imponer restricciones adicionales.
- No se puede relicenciar BenePDF como MIT, Apache o propietario mientras se
  enlace PyMuPDF bajo AGPL. Para hacerlo habría que adquirir una licencia
  comercial de Artifex o sustituir el motor PDF.
- Al distribuir solo código fuente no se aplican las obligaciones de
  relink de Qt que tendría un binario LGPL. Aun así, `THIRD_PARTY_NOTICES.md`
  documenta las licencias y las obligaciones que se aplicarían si se publicara
  un ejecutable.
- El CI sigue detectando fallos de empaquetado, pero no convierte el repositorio
  en una distribución binaria.
- Las fuentes Liberation se distribuyen con su `OFL.txt`; no se modifican.

## Alternativas descartadas

| Alternativa | Motivo para descartarla |
|---|---|
| MIT o Apache-2.0 | Requiere sustituir PyMuPDF o comprar una licencia comercial de Artifex; además, el cambio de motor afectaría a render, texto y redacción |
| Licencia propietaria | Requiere licencia comercial de Artifex para PyMuPDF y revisar la licencia comercial de Qt |
| `AGPL-3.0-or-later` | PyMuPDF declara la versión 3.0; la variante “or later” añade ambigüedad sobre versiones futuras y no aporta una ventaja práctica |
| Mantener el repositorio sin `LICENSE` | Deja el código en todos los derechos reservados y no permite reutilizarlo legalmente |
| Publicar también binarios | Añade obligaciones de distribución de código, avisos y reemplazo de Qt que el proyecto no necesita para su objetivo actual |

## Revisión

Esta decisión debe revisarse si:

- se publican binarios o Releases;
- se cambia de motor PDF;
- se adopta una licencia comercial de Artifex o de Qt;
- se añaden dependencias con licencias incompatibles con AGPL-3.0.

La documentación de licencias no sustituye una revisión legal independiente.
