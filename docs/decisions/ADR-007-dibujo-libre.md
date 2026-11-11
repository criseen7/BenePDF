# ADR-007 — Dibujo libre con trazos vectoriales

- **Estado:** aceptada
- **Fecha:** 2026-11-10

## Contexto

La iteración 7 añade RF-026: dibujar a mano alzada sobre la página, con color y
grosor configurables. Los trazos deben poder seleccionarse, moverse,
redimensionarse, eliminarse y deshacerse como el resto de objetos de edición,
sin modificar el PDF original y sin añadir dependencias.

El modelo de edición de ADR-002 representa cada objeto con un `page_index` y un
`PdfRect`. Un trazo no encaja del todo en ese contrato: su forma no es un
rectángulo, y moverlo o redimensionarlo debe transformar la geometría real y no
solo la caja que la contiene. Además, la exportación de ADR-003 inserta el
contenido nuevo antes de aplicar la rotación adicional y de reordenar páginas.

## Decisión

### Modelo de dominio

`bene.domain.editing` incorpora:

- `StrokeStyle(color, width)`: color `#rrggbb` y grosor en puntos PDF. El grosor
  debe ser finito y mayor que cero.
- `StrokeObject(object_id, page_index, points, style)`: una tupla de puntos en
  **coordenadas visibles de la página** (origen arriba-izquierda, con `/Rotate`
  y CropBox ya aplicados), la misma convención que el resto de objetos.
- `AddStrokeCommand(stroke_object)`, que comparte historial con los comandos de
  texto, imagen, redacción y página.

`StrokeObject.rect` no se almacena: se calcula como la caja de los puntos
ampliada por `width / 2`. Así un punto aislado o una línea perfectamente
horizontal siguen teniendo un área seleccionable no vacía. Los puntos se
normalizan a `float` al construir el objeto y se rechazan valores no finitos.

### Transformaciones

Mover un trazo desplaza todos sus puntos la misma distancia. Redimensionar
escala los puntos proporcionalmente respecto a la caja interior (la caja visible
sin el margen del grosor) y **conserva el grosor**. Escalar el grosor junto con
la caja haría que un trazo fino se volviera ilegible al reducirse y que el
resultado dependiera del número de asas arrastradas. El resto de objetos siguen
usando `MoveObjectCommand` y `ResizeObjectCommand`; el dominio elige la
transformación según el tipo.

### Lienzo e interfaz

`CanvasTool.DRAW` captura los puntos entre `mousePress` y `mouseRelease`,
descarta muestras a menos de `MIN_DRAW_DISTANCE` píxeles de la anterior para no
generar trazos con miles de puntos casi idénticos y emite
`stroke_requested(points, style)`. La herramienta permanece activa después de
cada trazo para dibujar varios seguidos; se sale con **Seleccionar** o con otra
herramienta.

La barra **Dibujo** contiene la acción `Dibujar` (`Ctrl+Shift+D`), un selector
de grosor de `0.5` a `50` pt y un botón de color que abre `QColorDialog`. El
texto sigue usando el diálogo de RF-007; la ventana recuerda el último
`TextStyle` aceptado para prefijar la siguiente apertura.

### Exportación

El adaptador PyMuPDF convierte cada punto visible al espacio sin rotar de la
página con la misma matriz que los rectángulos y dibuja:

- un trazo de varios puntos con `page.draw_polyline(..., lineCap=1,
  lineJoin=1)`, para que los extremos y las uniones sean redondeados;
- un punto aislado con `page.draw_circle(..., width=0)`, usando el relleno para
  definir el diámetro y evitar que un borde del mismo grosor duplique el tamaño.

Los trazos se insertan como vectores, no como imágenes: el archivo exportado
conserva la calidad al hacer zoom y no crece con un mapa de bits por trazo. El
orden de exportación no cambia respecto a ADR-006:

1. Reemplazos de imagen y redacciones.
2. Texto, imágenes y trazos nuevos.
3. Rotación adicional de cada página.
4. `document.select(list(arrangement.order))`.

Los trazos de páginas eliminadas permanecen en la sesión para que deshacer
funcione, pero no se exportan. `ExportResult.stroke_count` los cuenta para el
resumen y el registro.

## Consecuencias

- El PDF original sigue siendo inmutable y la exportación mantiene el temporal
  validado y el reemplazo atómico de ADR-003.
- Los trazos se seleccionan y transforman con las mismas herramientas que el
  resto de objetos, sin duplicar la lógica de selección del lienzo.
- El grosor no cambia al redimensionar; para engrosar un trazo hay que dibujarlo
  de nuevo o cambiar el estilo antes de crearlo.
- Un trazo con muchísimos puntos aumenta el tamaño del contenido vectorial y el
  coste de la vista previa; la deduplicación del lienzo lo limita en la práctica.
- No hay líneas rectas, flechas, formas ni resaltador en esta iteración: solo
  trazo libre. Quedan para el backlog.
- El dibujo se captura con el ratón o el panel táctil; no hay presión ni
  inclinación del lápiz.
