# ADR-006 — Disposición de páginas, búsqueda y reemplazo de imagen

- **Estado:** aceptada
- **Fecha:** 2026-11-10

## Contexto

La iteración 6 incorpora RF-013 (reemplazar una imagen incrustada), RF-020
(buscar texto), RF-021 (rotar, extraer, reordenar y eliminar páginas) y RF-022
(información del documento). Todas estas funciones conviven con el modelo de
edición en memoria de ADR-002 y con la exportación atómica de ADR-003.

El reto principal es que los objetos de edición (`TextObject`, `ImageObject`,
`RedactionObject`, `ImageReplacementObject`) guardan un `page_index`. Si el
usuario reordena o elimina páginas, ese índice no puede convertirse en una
posición de salida: los objetos deben seguir apuntando a la página original
aunque el orden cambie o la página desaparezca temporalmente.

## Decisión

### Índices fuente estables

La disposición de la copia de trabajo vive en `bene.domain.pages.PageArrangement`:

- `page_count` es el número de páginas del PDF original.
- `order` es una tupla de **índices fuente** en el orden de salida.
- Las páginas ausentes de `order` están eliminadas de la copia de trabajo.
- `rotations` guarda solo la rotación adicional distinta de cero de cada página
  fuente y se expone como una vista de solo lectura.

La disposición es inmutable. Las operaciones devuelven una disposición nueva y
los comandos de página (`RotatePageCommand`, `MovePageCommand`,
`DeletePageCommand`) comparten el historial con los comandos de objeto. Al
deshacer o rehacer, la sesión reconstruye a la vez los objetos y la disposición.

`PageArrangement.subset(...)` crea una disposición con una selección de páginas
para extraerlas a un archivo nuevo sin modificar la sesión, el historial ni el
estado «sin exportar».

### Exportación

El adaptador PyMuPDF parte siempre de una copia limpia del original. El orden es:

1. Reemplazos de imagen y redacciones sobre las páginas fuente presentes.
2. Texto e imágenes nuevas.
3. Rotación adicional de cada página.
4. `document.select(list(arrangement.order))` para reordenar y eliminar.
5. Guardado con `garbage=4` para que el contenido redactado no quede en el archivo.

Los objetos de páginas eliminadas se conservan en la sesión para que deshacer
funcione, pero no se exportan.

### Búsqueda

La búsqueda se ejecuta en segundo plano con un trabajador de un solo hilo y un
token por consulta. Si el usuario lanza otra búsqueda, el resultado anterior se
descarta. Las coordenadas que devuelve el motor se convierten al espacio visible
de la página (con `/Rotate` y CropBox ya aplicados), igual que los rectángulos de
los objetos. La búsqueda no incluye OCR.

### Reemplazo de imagen

El dominio guarda un `ImageReplacementObject` con un `image_id` opaco y los
bytes de la imagen nueva. El adaptador interpreta ese identificador como un
`xref` de PyMuPDF y llama a `Page.replace_image(xref, stream=...)` al exportar.
Las imágenes en línea, dentro de formularios o sin un `xref` fiable se omiten en
la detección. Si un `xref` se comparte entre páginas, el diálogo avisa de que el
reemplazo afectará a todas ellas.

## Consecuencias

- Los objetos de edición sobreviven a reordenaciones y eliminaciones sin
  reescribir sus índices.
- Deshacer/rehacer restaura objetos y disposición en el mismo paso.
- El render, la caché y las miniaturas se indexan por página fuente y rotación
  total, no por posición de salida.
- La barra de estado y el selector de página usan posiciones de salida; cuando
  hay páginas eliminadas se muestra además la página original.
- Una coincidencia de búsqueda en una página eliminada sigue en la lista, pero
  no se puede navegar a ella y se avisa al usuario.
- Reemplazar una imagen compartida cambia todas sus apariciones, tal como indica
  el diálogo.
- La búsqueda no encuentra texto en escaneos sin OCR; eso queda para la
  iteración 7.
