# Changelog

Todos los cambios visibles del proyecto se registran aquí. El formato sigue
[Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y el proyecto usa
versionado semántico mientras no se publique una versión distribuible.

## [Sin publicar]

### Añadido

- Zoom con `Ctrl`+rueda del ratón sobre la página, además de los botones y los
  atajos existentes.
- Marca `*` en el título de la ventana cuando hay cambios sin exportar.
- Hoja de ruta principal
  `BenePDF_Plan_Mejoras_Evolucion_Correcciones.md` enlazada desde el README y
  `PLAN.md`.
- Este changelog.

### Corregido

- La redacción elimina las anotaciones y los campos de formulario cuya área
  intersecta la región; antes podían conservar texto o valores extraíbles.
- Se añadieron pruebas de redacción de anotaciones, formularios, texto
  parcialmente intersectado y vectores.

### Documentación

- `ADR-003` explica la eliminación de anotaciones y campos y limita el alcance:
  la redacción por región no sanea metadatos ni archivos adjuntos.
- `README.md` y `README.es.md` documentan el zoom con rueda, la marca del
  título y las limitaciones de la redacción.
- `AGENTS.md` y `PLAN.md` recogen la hoja de ruta, los nuevos invariantes y la
  revisión de integridad.

## [0.1.0] - 2026-11-10

### Añadido

- Iteraciones 1 a 7: apertura y visualización de PDF, navegación, zoom, rotación
  de vista, miniaturas, edición en memoria de texto e imágenes, redacción
  permanente, exportación atómica, búsqueda, información del documento,
  operaciones de páginas, reemplazo de imágenes y dibujo libre vectorial.
- Empaquetado con PyInstaller e integración continua en Windows y Ubuntu.

[Sin publicar]: https://github.com/criseen7/BenePDF/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/criseen7/BenePDF/releases/tag/v0.1.0
