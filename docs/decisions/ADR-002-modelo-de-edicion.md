# ADR-002 — Modelo de edición: comandos en memoria y aplicación al exportar

- **Estado:** aceptada
- **Fecha:** 2026-10-24

## Contexto

La especificación exige deshacer/rehacer durante la sesión (RF-014), no modificar el original (RN-001), representar los cambios como operaciones reversibles (RN-008) y aplicar de verdad las redacciones antes de exportar (RN-004).

Aplicar cada edición directamente al documento en memoria tiene dos problemas:

1. `Page.insert_text()` escribe operadores en el flujo de contenido y no se puede revertir de forma individual.
2. `Page.apply_redactions()` es destructivo e irreversible.

## Decisión

La sesión de edición se modela como una **lista ordenada de comandos inmutables** sobre un documento que permanece intacto:

- `AddTextCommand`, `MoveObjectCommand`, `ResizeObjectCommand`, `AddImageCommand`, `AddRedactionCommand`.
- Cada comando contiene índice de página, coordenadas en puntos PDF (origen arriba-izquierda) y sus parámetros.
- El índice del historial define qué comandos están activos; deshacer y rehacer solo mueven ese índice.
- **Vista previa:** se renderiza la página base con PyMuPDF y se dibujan encima los comandos activos con `QPainter`. Es rápida y suficiente para colocar y mover elementos.
- **Vista previa exacta:** a petición, se aplican los comandos a una copia en memoria del documento y se renderiza el resultado real. Sirve para comprobar tipografías y redacciones antes de exportar.
- **Exportación:** se aplican todos los comandos activos a una copia, se escribe a un archivo temporal, se reabre y valida, y solo entonces se reemplaza el destino de forma atómica.

La redacción nunca se simula al exportar: `AddRedactionCommand` ejecuta `add_redact_annot()` + `apply_redactions()` sobre la copia.

## Consecuencias

- Deshacer/rehacer es O(1) y no puede corromper el documento.
- El original permanece intacto hasta que el usuario exporte y confirme un reemplazo.
- La vista previa por capas puede diferir del PDF final en tipografías y ajuste de línea; la interfaz lo advierte y ofrece la vista previa exacta.
- La exportación cuesta un render completo del documento, aceptable porque es una acción explícita.
- La coordinación entre zoom, rotación de vista y coordenadas PDF queda en un único componente (`CoordinateMapper`), que se implementa en la iteración 2 y se prueba de forma unitaria.

## Alternativas descartadas

| Alternativa | Motivo |
|---|---|
| Mutar el documento en cada edición | Sin deshacer fiable; la redacción destruye información de forma irreversible |
| Guardar una copia completa del documento por operación | Memoria y tiempo proporcionales al tamaño del PDF y al número de ediciones |
| Anotaciones PDF en lugar de comandos | El usuario espera cambios permanentes, no comentarios; además no resuelve la redacción |
