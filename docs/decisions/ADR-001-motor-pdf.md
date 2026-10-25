# ADR-001 — Motor PDF: PyMuPDF 2.0

- **Estado:** aceptada
- **Fecha:** 2026-10-24
- **Contexto del proyecto:** uso personal, sin distribución

## Contexto

La aplicación necesita, además del renderizado de páginas:

- insertar texto con fuente, tamaño y color en coordenadas de página;
- insertar y transformar imágenes;
- aplicar redacción real (eliminar contenido subyacente, no taparlo);
- extraer texto para detectar páginas escaneadas.

El requisito RNF-018 exige revisar las licencias antes de distribuir. La especificación deja la elección del motor como decisión pendiente.

## Decisión

Se usa **PyMuPDF 2.0** (`pymupdf`) como motor PDF inicial, encapsulado tras el puerto `PdfEngine`. La versión se fija en `>=2.0,<3.0`.

Se eligió 2.0 y no 1.28.x porque 2.0 corrige un fallo de `apply_redactions()` introducido en la rama 1.28 (texto mostrado con `'` tras `TL`/`Td` que no se eliminaba). La redacción es una función central del producto y no admite ese fallo.

## Consecuencias

- El proyecto queda bajo las condiciones **AGPL-3.0**: es válido para uso personal o para publicar el código bajo AGPL, pero no para distribuir un binario cerrado. Si se decide distribuir, este ADR debe revisarse antes de publicar.
- Solo `infrastructure/pdf/pymupdf_engine.py` importa `pymupdf`. El resto del código depende del puerto, de modo que sustituir el motor no afecta a la interfaz ni al dominio.
- El módulo correcto es `pymupdf`; `import fitz` sigue existiendo pero emite `FutureWarning`.
- PyMuPDF 2.0 arrastra dependencias que el MVP no usa (`pymupdf-layout`, `pymupdf4llm`, `onnxruntime`, `numpy`). Medido en Windows con el entorno completo: 992 MB de `.venv`, de los cuales 105 MB son PyMuPDF y 99 MB sus extras. No se pueden excluir, pero solo afectan al tamaño de desarrollo: PyInstaller empaquetará lo que se importe.
- Al empaquetar con PyInstaller habrá que incluir los binarios de MuPDF (iteración 4).
- No se ejecuta JavaScript ni contenido activo del PDF: PyMuPDF no lo hace por defecto.

## Alternativas descartadas

| Alternativa | Motivo para descartarla |
|---|---|
| pypdfium2 + pikepdf + pypdf | Licencias permisivas, pero no ofrece redacción ni inserción de texto con la misma madurez; multiplica el trabajo de la iteración 3 |
| pdf-lib / PyPDF2 | Sin renderizado ni redacción |
| Ghostscript vía subprocess | Dependencia externa pesada, difícil de empaquetar y de previsualizar |

## Revisión

Si el proyecto pasa a distribuirse, evaluar de nuevo `pypdfium2` + `pikepdf` o una licencia comercial de Artifex. La decisión afecta solo al adaptador.
