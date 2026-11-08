# ADR-003 — Exportación atómica y redacción permanente

- **Estado:** aceptada
- **Fecha:** 2026-10-26

## Contexto

La iteración 3 materializa por primera vez los comandos de edición en un archivo
PDF. La especificación exige que el original nunca se modifique (RN-001), que la
redacción elimine el contenido subyacente y no solo lo cubra (RN-003, RN-004,
RNF-008) y que la escritura sea segura aunque el proceso falle a mitad
(RNF-005). También hay que respetar las páginas con `/Rotate`, donde el modelo
de edición usa coordenadas visibles y PyMuPDF usa coordenadas sin rotar.

## Decisión

### Copia limpia y destino nuevo

La exportación parte de una **copia limpia del archivo original**, no del
documento abierto en el visor. El adaptador rechaza cualquier destino que
resuelva a la misma ruta que el original; el caso de uso `ExportDocument` hace
la misma comprobación antes de llamar al motor. Así se impide sobrescribir el
original incluso si el diálogo de guardado confirma una ruta existente.

### Escritura atómica

1. Se crea un archivo temporal en **el mismo directorio** que el destino, para
   que el reemplazo no cruce sistemas de archivos.
2. Se aplican las ediciones y se guarda en el temporal con `garbage=4` y
   `deflate=True`.
3. Se **reabre el temporal** y se valida que es un PDF, que conserva el número
   de páginas y que no quedan anotaciones de redacción.
4. Solo entonces se reemplaza el destino con `Path.replace()`, que en Windows y
   Linux es atómico dentro del mismo volumen.
5. Ante cualquier error, el temporal se elimina y el destino no se toca.

### Orden de aplicación y rotación

En cada página se aplican primero **todas las redacciones** y después los
textos e imágenes nuevos. Esto permite el flujo «redactar una región y escribir
el texto corregido encima».

Las coordenadas del modelo son las visibles (después de `/Rotate`). Antes de
llamar a PyMuPDF se convierten teniendo en cuenta también el origen del
CropBox:

```
M  = Matrix(1, 0, 0, -1, -cropbox.x0, cropbox.y1) * page.rotation_matrix
rect_pdf  = rect_visible * ~M
rect_page = rect_pdf * page.transformation_matrix
```

Los nuevos elementos se giran para quedar derechos en la página visible:

- texto: `rotate=page.rotation`;
- imagen: `rotate=page.rotation`, con `keep_proportion=False`.

La versión anterior usaba `rect * page.derotation_matrix` y
`rotate=(360 - page.rotation) % 360` para el texto. Con esas fórmulas el texto
salía invertido y las imágenes se desplazaban en páginas recortadas o rotadas;
las pruebas de regresión de la iteración 4 cubren las cuatro rotaciones y un
CropBox desplazado.

### Redacción de texto, vectores e imágenes

- Texto: `PDF_REDACT_TEXT_REMOVE`.
- Vectores: `PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED`.
- Imágenes: `PDF_REDACT_IMAGE_PIXELS`, que elimina los píxeles de la región y
  conserva el resto de la imagen. Se descartó `PDF_REDACT_IMAGE_REMOVE` porque
  borraba la página escaneada completa al tocar una sola región.
- El rectángulo se rellena de negro para que la vista previa y el resultado
  coincidan visualmente.

### PDF cifrados

La exportación de un PDF cifrado se rechaza con un `ExportError` explícito y la
acción queda deshabilitada. PyMuPDF solo puede conservar la protección con la
contraseña de propietario, que la aplicación no solicita ni guarda. Exportar sin
cifrar sería una degradación de seguridad silenciosa, así que no se hace.

## Consecuencias

- El original permanece intacto aunque falle la exportación.
- El archivo exportado se puede reabrir y contiene los cambios.
- Las pruebas comprueban por extracción de texto que el contenido redactado ya
  no está, y por renderizado que la región queda cubierta.
- En un escaneo, la redacción elimina solo los píxeles de la región; el resto de
  la imagen se conserva.
- La redacción puede afectar a objetos que se solapen total o parcialmente con
  la región; por eso se pide confirmación al marcarla y otra al exportar.
- Los PDF cifrados no se pueden exportar en esta iteración.

## Alternativas descartadas

| Alternativa | Motivo |
|---|---|
| Guardar directamente sobre el original | Viola RN-001 y no permite deshacer tras el guardado |
| Escribir el destino sin temporal | Un fallo a mitad deja un PDF truncado |
| Validar solo el tamaño del archivo | No detecta un PDF corrupto o con redacciones pendientes |
| `PDF_REDACT_IMAGE_REMOVE` | Borra la imagen entera; destruye escaneos al redactar una región pequeña |
| Exportar PDF cifrados sin cifrar | Degrada la protección sin avisar al usuario |
| Aplicar ediciones al documento del visor | Mezcla la vista previa con el estado persistido y rompe deshacer |
