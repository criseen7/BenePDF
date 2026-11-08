# ADR-004 — Fuentes abiertas embebidas en la vista previa y la exportación

- **Estado:** aceptada
- **Fecha:** 2026-11-07

## Contexto

La iteración 3 usaba fuentes Base-14 en la exportación y dejaba que Qt eligiera
un sustituto del sistema para la vista previa. Eso producía tres problemas:

1. La vista previa y el PDF exportado medían distinto, así que un texto que
   parecía caber podía desbordarse al exportar (o al contrario).
2. La codificación Base-14 no cubre el euro (`€`), que se convertía en `?`.
3. La apariencia dependía de las fuentes instaladas en cada equipo.

## Decisión

Se empaquetan tres fuentes abiertas con licencia SIL Open Font License:

| Nombre lógico | Archivo | Equivalente métrico |
|---|---|---|
| `Helvetica` | `LiberationSans-Regular.ttf` | Arial / Helvetica |
| `Times-Roman` | `LiberationSerif-Regular.ttf` | Times New Roman |
| `Courier` | `LiberationMono-Regular.ttf` | Courier New |

Los TTF y la licencia viven en `src/bene/assets/fonts` y se declaran como
`package-data`. El nombre lógico del dominio no cambia: `infrastructure/fonts.py`
resuelve la ruta y el alias, y `presentation/fonts.py` registra la misma familia
en `QFontDatabase` para la vista previa. La exportación incrusta el TTF con
`fontfile` en `insert_textbox`.

Si el recurso no está disponible, el adaptador cae en la fuente Base-14
correspondiente y la aplicación sigue funcionando; la vista previa usa entonces
el nombre lógico del sistema.

## Consecuencias

- La vista previa y la exportación comparten métricas y familia tipográfica.
- `€`, acentos, griego y cirílico se conservan al exportar.
- Antes de insertar texto se comprueba cada carácter con `Font.has_glyph`; si
  falta algún glifo (por ejemplo, emoji o CJK), la exportación se bloquea con un
  mensaje que identifica la página y el objeto.
- El PDF exportado incorpora el subconjunto de la fuente, así que no depende de
  las fuentes instaladas en el equipo que lo abra.
- El repositorio crece unos 1,1 MB por las tres fuentes regulares. No se
  incluyen negrita ni cursiva porque el modelo de edición todavía no las ofrece.

## Alternativas descartadas

| Alternativa | Motivo |
|---|---|
| Seguir usando Base-14 | No cubre `€` y no coincide con las métricas de Qt |
| Usar las fuentes del sistema | La apariencia y el ajuste cambian entre equipos; Arial y Times no son redistribuibles |
| Incrustar una única fuente | Se perdería la distinción entre palo seco, serif y monoespaciada |
| Dibujar el texto como trazados | Imposibilita seleccionar y buscar el texto exportado |
