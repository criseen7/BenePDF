# BenePDF --- Plan de mejoras, evolución y correcciones

**Documento:** Hoja de ruta técnica y de producto\
**Proyecto:** [criseen7/BenePDF](https://github.com/criseen7/BenePDF)\
**Fecha:** 10 de noviembre de 2026\
**Propósito:** convertir BenePDF en una aplicación de escritorio para
PDF robusta, verificable, mantenible y distribuible.

> **Nota de alcance:** este documento transforma la revisión preliminar
> del proyecto en un plan de trabajo. Los puntos descritos son
> recomendaciones y criterios de aceptación, no afirmaciones de que
> exista un defecto confirmado en el código. Antes de modificar módulos,
> contrasta cada punto con la implementación actual, los tests y las
> dependencias.

------------------------------------------------------------------------

## 1. Objetivos

BenePDF debe evolucionar de un proyecto funcional a un producto que
pueda instalarse, utilizarse y probarse de forma fiable.

### Objetivos principales

1.  Proteger la integridad del documento original y del resultado
    exportado.
2.  Garantizar que las operaciones de edición se representen
    correctamente en pantalla y en el PDF final.
3.  Asegurar que la redacción elimine realmente la información
    seleccionada, no solo la oculte visualmente.
4.  Mantener la interfaz responsiva durante operaciones costosas.
5.  Establecer pruebas reproducibles de funcionalidad, seguridad,
    rendimiento y compatibilidad.
6.  Resolver la estrategia de licenciamiento antes de distribuir
    binarios.
7.  Mejorar la experiencia de usuario y la documentación del producto.
8.  Añadir funcionalidades avanzadas únicamente cuando la base sea
    estable.

### Principios de implementación

-   Priorizar corrección e integridad sobre cantidad de funcionalidades.
-   Mantener las dependencias orientadas hacia el dominio y los casos de
    uso.
-   Evitar lógica de negocio dentro de widgets o ventanas.
-   No introducir abstracciones sin una necesidad concreta.
-   Mantener operaciones destructivas fuera del flujo de edición
    interactiva siempre que sea posible.
-   Validar los archivos generados antes de reemplazar cualquier
    destino.
-   Tratar todo PDF externo como entrada no confiable.
-   Medir rendimiento con documentos de prueba reproducibles.

------------------------------------------------------------------------

## 2. Diagnóstico y áreas de trabajo

  ------------------------------------------------------------------------
  Área                  Objetivo                                 Prioridad
  --------------------- --------------------- ----------------------------
  Integridad de         Evitar pérdida o                                P0
  exportación           corrupción de         
                        documentos            

  Redacción permanente  Eliminar contenido                              P0
                        subyacente y          
                        verificar el          
                        resultado             

  Geometría y           Evitar                                          P0
  coordenadas           desplazamientos y     
                        errores de            
                        escala/rotación       

  Licenciamiento        Definir condiciones                             P0
                        legales de            
                        distribución          

  Pruebas automatizadas Detectar regresiones                            P0
                        y documentar          
                        cobertura             

  Concurrencia y        Evitar bloqueos y                               P1
  memoria               consumo descontrolado 

  Empaquetado           Validar instalación                             P1
                        en entornos limpios   

  UX y accesibilidad    Mejorar la eficiencia                           P1
                        y claridad de la      
                        interfaz              

  OCR y procesamiento   Ampliar las                                     P2
  por lotes             capacidades del       
                        producto              

  Firma digital         Añadir flujos                                   P3
                        documentales          
                        avanzados             
  ------------------------------------------------------------------------

**P0:** bloqueante para una versión estable o distribución pública.\
**P1:** importante para calidad de producto.\
**P2:** evolución funcional posterior a la estabilización.\
**P3:** funcionalidad avanzada que requiere análisis específico.

------------------------------------------------------------------------

# 3. Correcciones prioritarias (P0)

## 3.1. Integridad y seguridad de exportación

### Problema que se debe prevenir

Una exportación interrumpida, un error de escritura o una validación
insuficiente puede dejar un archivo incompleto o reemplazar un documento
válido por uno defectuoso.

### Mejoras requeridas

-   Escribir primero en un archivo temporal ubicado, preferentemente, en
    el mismo sistema de archivos que el destino.
-   No sobrescribir el archivo original de entrada.
-   Cerrar correctamente el documento y liberar los recursos antes de
    validar o reemplazar.
-   Volver a abrir el temporal con el motor PDF.
-   Comprobar que el documento se puede leer y que su estructura básica
    es coherente.
-   Validar el número de páginas esperado y las operaciones aplicadas.
-   Sustituir el destino mediante una operación atómica cuando el
    sistema de archivos lo permita.
-   Mantener el archivo anterior si falla cualquier paso.
-   Limpiar temporales abandonados sin eliminar archivos que todavía
    estén en uso.
-   Registrar errores técnicos sin incluir texto sensible del documento
    en los logs.

### Flujo recomendado

``` text
Solicitud de exportación
        |
        v
Validar estado y destino
        |
        v
Crear archivo temporal
        |
        v
Aplicar operaciones
        |
        v
Cerrar y liberar recursos
        |
        v
Reabrir y validar temporal
        |
   +----+----+
   |         |
 Válido    Inválido
   |         |
   v         v
Reemplazo  Conservar destino
atómico    original y reportar error
   |
   v
Confirmar exportación
```

### Criterios de aceptación

-   Si falla la exportación, el documento de destino anterior permanece
    intacto.
-   El documento original no se modifica por una exportación normal.
-   Un PDF exportado puede abrirse nuevamente.
-   El número de páginas coincide con el resultado esperado.
-   Los temporales se limpian de forma controlada.
-   Los errores se muestran al usuario con un mensaje comprensible y se
    registran técnicamente.

## 3.2. Redacción permanente de información

### Riesgo

Dibujar un rectángulo opaco encima del contenido no equivale a redactar.
El texto, las imágenes u otros objetos podrían seguir presentes en el
archivo.

### Mejoras requeridas

-   Diferenciar explícitamente una marca visual de redacción de una
    redacción aplicada y permanente.
-   Aplicar la operación de redacción mediante las capacidades
    apropiadas del motor PDF.
-   Considerar texto, imágenes, trazos vectoriales y contenido
    parcialmente intersectado.
-   Revisar anotaciones, formularios, capas, metadatos y archivos
    adjuntos cuando el alcance de la función lo requiera.
-   Definir el comportamiento ante documentos cifrados, protegidos o con
    estructuras no compatibles.
-   No declarar éxito si la operación no pudo aplicarse o verificarse.
-   Informar al usuario que una redacción aplicada puede ser
    irreversible.

### Suite de pruebas de redacción

Crear PDFs sintéticos con:

1.  Texto dentro del área seleccionada.
2.  Texto parcialmente intersectado.
3.  Texto con rotación.
4.  Imágenes con información sensible.
5.  Vectores y líneas superpuestos.
6.  Anotaciones y comentarios.
7.  Formularios y campos de texto.
8.  Capas opcionales, cuando el motor las soporte.
9.  Metadatos y adjuntos de prueba.
10. Varias páginas y distintas geometrías de página.

### Verificaciones posteriores

-   Extraer texto del documento resultante y comprobar que el contenido
    objetivo ya no aparece.
-   Renderizar la página y verificar el resultado visual.
-   Comprobar que no se puede recuperar la región original desde la
    imagen resultante.
-   Inspeccionar los objetos relacionados con la región redactada.
-   Cerrar y volver a abrir el PDF antes de realizar las verificaciones.

**Limitación importante:** ninguna prueba aislada demuestra que toda
información sensible haya desaparecido de cualquier estructura posible
del PDF. Documenta el alcance de las garantías y las estructuras que se
verifican.

## 3.3. Transformaciones geométricas y coordenadas

### Riesgo

El visor, Qt y el documento PDF pueden utilizar sistemas de coordenadas
diferentes. El zoom, la rotación, el desplazamiento, el escalado HiDPI y
los límites de página pueden provocar errores de posición.

### Mejoras requeridas

Centralizar las transformaciones en un componente independiente. Evitar
cálculos duplicados en widgets, herramientas y comandos.

Estructura orientativa:

``` text
domain/
└── geometry/
    ├── point.py
    ├── rectangle.py
    ├── page_geometry.py
    └── coordinate_transform.py
```

El nombre y ubicación definitivos deben respetar la arquitectura actual
del repositorio.

### Casos de prueba

-   Rotación de 0°, 90°, 180° y 270°.
-   Diferentes niveles de zoom.
-   Páginas con tamaños distintos.
-   CropBox y MediaBox diferentes.
-   Desplazamiento horizontal y vertical del visor.
-   Escalado HiDPI.
-   Selecciones en los bordes de página.
-   Coordenadas negativas o fuera del área visible.
-   Rectángulos con ancho o alto cero.
-   Transformaciones de ida y vuelta.

### Criterio matemático

Para una coordenada PDF (p), la transformación hacia la interfaz y su
inversa deben recuperar el punto original dentro de una tolerancia:

\[ p' = T\^{-1}(T(p)) \]

\[ `\lVert `{=tex}p' - p `\rVert `{=tex}`\leq `{=tex}`\varepsilon`{=tex}
\]

La tolerancia debe definirse según la unidad, la escala y la precisión
esperada; no debe elegirse arbitrariamente.

## 3.4. Política de licenciamiento

Antes de publicar ejecutables o distribuir BenePDF, documentar las
licencias y obligaciones de todas las dependencias.

Revisar específicamente:

-   PyMuPDF y las condiciones AGPL/comerciales aplicables a la versión
    utilizada.
-   PySide6 y la alternativa de licencia correspondiente.
-   Dependencias transitivas.
-   Recursos gráficos, fuentes e iconos.
-   Herramientas incluidas en el empaquetado.
-   Avisos de copyright y textos de licencia.

### Decisiones que deben quedar documentadas

-   Licencia elegida para el código de BenePDF.
-   Si la distribución será open source o propietaria.
-   Compatibilidad de las dependencias con ese modelo.
-   Obligaciones al distribuir binarios.
-   Inclusión de avisos y licencias de terceros.

**No asumir compatibilidad legal por el mero hecho de que una
dependencia sea gratuita.** Si se contempla distribución comercial o un
modelo propietario, obtener asesoría especializada antes de publicar.

------------------------------------------------------------------------

# 4. Arquitectura y mantenibilidad (P1)

## 4.1. Reforzar las fronteras entre capas

Conservar la separación documentada entre dominio, aplicación,
infraestructura y presentación.

Responsabilidades esperadas:

  -----------------------------------------------------------------------
  Capa                    Debe contener           Debe evitar
  ----------------------- ----------------------- -----------------------
  Domain                  Entidades, reglas y     PySide6, acceso directo
                          objetos de valor        a disco o PyMuPDF

  Application             Casos de uso, puertos y Widgets y detalles de
                          coordinación            interfaz

  Infrastructure          Adaptadores PDF,        Reglas de negocio
                          almacenamiento, logs y  dispersas
                          OCR                     

  Presentation            Ventanas, widgets,      Manipulación directa
                          interacción y view      del documento
                          models                  

  Bootstrap               Construcción e          Lógica de negocio
                          inyección de            
                          dependencias            
  -----------------------------------------------------------------------

### Acciones

-   Revisar imports entre capas.
-   Evitar dependencias desde `domain` hacia `infrastructure` o
    `presentation`.
-   Definir interfaces para operaciones externas relevantes.
-   Inyectar dependencias en los casos de uso.
-   Mantener los adaptadores intercambiables cuando exista una razón
    real.
-   Evitar servicios globales y estado mutable compartido innecesario.

## 4.2. Contrato de comandos de edición

Cada comando debería tener un contrato explícito.

Campos o comportamientos a considerar:

-   Identificador único.
-   Parámetros inmutables.
-   Validación de precondiciones.
-   Aplicación sobre el estado de edición.
-   Información necesaria para revertir, si aplica.
-   Clasificación de reversibilidad.
-   Manejo de errores.
-   Requisitos de exportación.

Ejemplo conceptual:

``` python
from typing import Protocol


class EditCommand(Protocol):
    def validate(self, context) -> None: ...

    def apply(self, context) -> None: ...

    def undo(self, context) -> None: ...
```

Este fragmento es ilustrativo: adaptar nombres, tipos y contratos a la
implementación existente.

### Reglas

-   No todos los comandos tienen que ser reversibles.
-   Las operaciones destructivas deben identificarse claramente.
-   El historial debe tener límites de memoria o tamaño.
-   Una operación fallida no debe dejar el estado parcialmente
    modificado.
-   El orden de ejecución debe ser determinista.
-   Deben existir pruebas de secuencias de comandos, no solo de comandos
    individuales.

## 4.3. Estado del documento

Definir claramente los estados del documento y sus transiciones.

Estados orientativos:

-   `CLOSED`
-   `LOADING`
-   `READY`
-   `MODIFIED`
-   `EXPORTING`
-   `ERROR`

Asegurar que:

-   No se edite un documento mientras se está cerrando.
-   No se inicie una exportación duplicada accidentalmente.
-   El cierre de la ventana gestione tareas activas.
-   Los errores no dejen la interfaz bloqueada.
-   El estado de cambios pendientes se actualice al ejecutar undo/redo.

## 4.4. Gestión de errores

Separar errores de dominio, aplicación e infraestructura.

Ejemplos:

-   Documento inválido.
-   Contraseña requerida.
-   Operación no soportada.
-   Página inexistente.
-   Archivo bloqueado.
-   Permisos insuficientes.
-   Espacio insuficiente.
-   Error de renderizado.
-   Cancelación de tarea.
-   Fallo de exportación.

Los mensajes al usuario deben ser accionables. Los logs deben incluir
contexto técnico suficiente, pero no contenido confidencial del PDF.

------------------------------------------------------------------------

# 5. Concurrencia, rendimiento y memoria (P1)

## 5.1. Procesamiento en segundo plano

Mantener las operaciones costosas fuera del hilo principal de Qt.

Candidatas:

-   Renderizado de páginas.
-   Generación de miniaturas.
-   OCR.
-   Exportación.
-   Procesamiento por lotes.
-   Análisis de documentos.

### Requisitos

-   Comunicación segura entre trabajadores y GUI mediante señales y
    mecanismos de Qt.
-   Cancelación cuando sea técnicamente posible.
-   Progreso y estado visibles.
-   Manejo de excepciones dentro del trabajador.
-   Liberación determinista de documentos y recursos.
-   Evitar actualizar widgets directamente desde hilos secundarios.
-   Evitar iniciar trabajos duplicados para una misma página y
    configuración.

## 5.2. Caché de renderizado

Evaluar una caché LRU con límite de memoria.

La clave de caché debería considerar, como mínimo:

-   Identidad de documento o sesión.
-   Índice de página.
-   Nivel de zoom o escala.
-   Rotación.
-   Parámetros de renderizado.
-   Versión del documento o estado de edición.

Invalidar entradas cuando cambien las operaciones que afectan a la
página.

No utilizar únicamente el índice de página como clave: podría devolver
una imagen obsoleta.

## 5.3. Plan de benchmarking

Crear documentos de prueba reproducibles:

  Perfil       Documento                             Propósito
  ------------ ------------------------------------- -----------------------
  Pequeño      5 páginas con texto                   Apertura y navegación
  Mediano      100 páginas mixtas                    Uso cotidiano
  Grande       500 páginas                           Escalabilidad
  Escaneado    100 páginas de imagen                 Renderizado y OCR
  Complejo     Vectores, transparencias e imágenes   Casos costosos
  Patológico   Archivo inválido o muy pesado         Robustez y límites

Registrar:

-   Tiempo hasta la primera página visible.
-   Tiempo de renderizado por página.
-   Tiempo de generación de miniaturas.
-   Memoria máxima.
-   Tiempo de exportación.
-   Tiempo de apertura.
-   Comportamiento durante navegación rápida.
-   Tiempo de cancelación de tareas.

No fijar objetivos numéricos hasta obtener una línea base en hardware
documentado. Después, establecer umbrales de regresión.

## 5.4. Límites de recursos

Definir límites configurables y mensajes claros para:

-   Tamaño máximo de archivo.
-   Número máximo de páginas procesadas simultáneamente.
-   Resolución máxima de renderizado.
-   Memoria de caché.
-   Número de trabajos en cola.
-   Tiempo de espera de operaciones cuando corresponda.

Los límites deben evitar bloqueos y consumo excesivo, sin impedir
innecesariamente el uso de documentos legítimos.

------------------------------------------------------------------------

# 6. Experiencia de usuario (P1)

## 6.1. Mejoras de interfaz

-   Añadir indicadores claros de documento modificado.
-   Mostrar el estado de carga, renderizado y exportación.
-   Permitir cancelar operaciones largas cuando sea seguro.
-   Mejorar los mensajes de error.
-   Incorporar panel de propiedades contextual.
-   Mejorar navegación por miniaturas y páginas.
-   Añadir atajos de teclado coherentes.
-   Permitir zoom con rueda del ratón y controles accesibles.
-   Ofrecer tema claro y oscuro si la arquitectura visual lo permite.
-   Evitar diálogos innecesarios durante operaciones frecuentes.

## 6.2. Comparación antes/después

Implementar una vista de comparación que permita inspeccionar el
documento original y el resultado de edición.

Opciones:

-   Vista dividida.
-   Alternancia entre original y resultado.
-   Comparación por página.
-   Resaltado de diferencias visuales.

La comparación visual no sustituye la verificación estructural o de
seguridad de un PDF.

## 6.3. Accesibilidad y usabilidad

-   Etiquetas accesibles en botones e iconos.
-   Orden de tabulación lógico.
-   Atajos documentados.
-   Contraste suficiente.
-   Tamaños de controles adecuados.
-   Mensajes de estado que no dependan exclusivamente del color.
-   Pruebas con diferentes escalas de pantalla.

------------------------------------------------------------------------

# 7. Funcionalidades de evolución (P2/P3)

No comenzar estas funcionalidades hasta que los criterios P0 estén
satisfechos.

## 7.1. OCR local

**Prioridad:** P2\
**Tecnología candidata:** Tesseract.

Diseñar una abstracción para no acoplar los casos de uso a un motor
específico.

Flujo:

``` text
PDF escaneado
    |
    v
Renderizado de página
    |
    v
Motor OCR local
    |
    v
Texto + coordenadas + confianza
    |
    v
Revisión y corrección
    |
    v
Búsqueda y navegación
```

Requisitos:

-   Procesamiento local.
-   Selección de idiomas.
-   Indicador de progreso.
-   Cancelación.
-   Confianza por bloque o palabra, si el motor la proporciona.
-   Conservación de coordenadas.
-   Pruebas con escaneos de distintas calidades.
-   No modificar el documento original sin confirmación.

El OCR no debe prometer reconstrucción exacta del diseño original.

## 7.2. Búsqueda avanzada

-   Búsqueda por texto.
-   Navegación entre coincidencias.
-   Resaltado de resultados.
-   Búsqueda en documentos con OCR.
-   Filtros por página.
-   Opción para distinguir mayúsculas/minúsculas.
-   Manejo correcto de caracteres Unicode.

## 7.3. Procesamiento por lotes

Permitir ejecutar operaciones sobre varios PDFs:

-   Rotar páginas.
-   Extraer páginas.
-   Unir documentos.
-   Aplicar compresión.
-   Exportar páginas a imágenes.
-   Aplicar una configuración común.

Requisitos:

-   Vista previa de operaciones.
-   Validación individual de cada archivo.
-   Resultado y errores por documento.
-   No detener toda la cola por un único fallo, salvo que la operación
    requiera atomicidad global.
-   Evitar sobrescrituras accidentales.
-   Registro de resultados.

## 7.4. Compresión y optimización

-   Configuración de resolución de imágenes.
-   Compresión de imágenes.
-   Eliminación opcional de objetos no utilizados cuando sea seguro.
-   Comparación de tamaño antes/después.
-   Vista previa de calidad.
-   Preservación de texto y vectores cuando sea posible.
-   Advertencia ante pérdida de calidad.

## 7.5. Firma digital

Tratar la firma digital como un módulo separado de las firmas dibujadas
o imágenes de firma.

Investigar:

-   Certificados.
-   Almacenamiento seguro de claves.
-   Estándares PDF aplicables.
-   Sellos de tiempo.
-   Validación de cadena de confianza.
-   Revocación de certificados.
-   Cambios posteriores a la firma.
-   Compatibilidad con lectores externos.

La inserción de una imagen con apariencia de firma no debe presentarse
como firma criptográfica.

## 7.6. Protección mediante contraseña

-   Apertura de PDFs cifrados.
-   Configuración de cifrado y permisos cuando el motor lo soporte.
-   Gestión segura de contraseñas en memoria.
-   No escribir contraseñas en logs.
-   Mensajes claros sobre limitaciones de seguridad.
-   Pruebas de compatibilidad con lectores PDF externos.

------------------------------------------------------------------------

# 8. Estrategia de pruebas

## 8.1. Pirámide de pruebas

### Unitarias

Cubrir:

-   Entidades y objetos de valor.
-   Geometría.
-   Validaciones.
-   Comandos.
-   Historial undo/redo.
-   Transiciones de estado.
-   Reglas de exportación.

### Integración

Cubrir:

-   Adaptadores PyMuPDF.
-   Lectura y escritura.
-   Renderizado.
-   Redacción.
-   Extracción de texto.
-   Almacenamiento temporal.
-   Exportación y reapertura.

### Interfaz

Cubrir:

-   Apertura y cierre.
-   Navegación.
-   Selección de objetos.
-   Edición.
-   Undo/redo.
-   Estados de carga.
-   Errores.
-   Cancelación de operaciones.
-   Diálogos de exportación.

### Regresión

Mantener un conjunto versionado de PDFs sintéticos y resultados
esperados. Evitar depender exclusivamente de documentos externos cuya
estructura pueda cambiar.

## 8.2. Pruebas basadas en propiedades

Evaluar Hypothesis para probar:

-   Transformaciones geométricas.
-   Rectángulos y límites.
-   Secuencias de comandos.
-   Serialización de configuraciones.
-   Reglas de validación.

Ejemplo conceptual:

``` python
def test_coordinate_round_trip(point, transform):
    screen_point = transform.to_screen(point)
    recovered = transform.to_pdf(screen_point)

    assert distance(point, recovered) <= transform.tolerance
```

Adaptar el ejemplo a los tipos y utilidades reales del proyecto.

## 8.3. Cobertura

-   Medir cobertura de líneas y ramas.
-   Establecer umbrales por módulo.
-   Priorizar cobertura de lógica crítica, no solo el porcentaje global.
-   No excluir código importante para mejorar artificialmente el
    indicador.
-   Publicar el reporte en CI.

## 8.4. Matriz de plataformas

  Entorno             Validación requerida
  ------------------- ---------------------------------------------------
  Windows 10/11       Funcionalidad, GUI y ejecutable
  Ubuntu LTS          Funcionalidad, GUI y dependencias
  Linux CI headless   Pruebas automatizadas sin pantalla
  Máquina limpia      Instalación y ejecución sin entorno de desarrollo

No declarar soporte oficial para una plataforma hasta completar pruebas
reales en ella.

------------------------------------------------------------------------

# 9. CI/CD, empaquetado y releases

## 9.1. Pipeline recomendado

``` text
Push / Pull Request
       |
       v
Instalar dependencias
       |
       v
Ruff + Mypy
       |
       v
Pruebas unitarias
       |
       v
Pruebas de integración
       |
       v
Pruebas GUI disponibles
       |
       v
Construcción del paquete
       |
       v
Validación del artefacto
       |
       v
Publicación de resultados
```

Separar trabajos rápidos y lentos para mantener tiempos razonables.

## 9.2. Empaquetado

Antes de publicar un ejecutable:

-   Construir en un entorno limpio.
-   Verificar recursos, plugins y bibliotecas incluidas.
-   Comprobar apertura, edición y exportación.
-   Probar rutas con espacios y caracteres Unicode.
-   Probar permisos de escritura.
-   Verificar que no dependa de archivos del entorno de desarrollo.
-   Revisar avisos de antivirus y firma de código cuando corresponda.
-   Documentar tamaño y requisitos del paquete.

## 9.3. Releases

Cada versión debe incluir:

-   Número de versión.
-   Fecha.
-   Notas de cambios.
-   Correcciones conocidas.
-   Sistemas soportados.
-   Requisitos.
-   Hash SHA-256 de los artefactos.
-   Instrucciones de instalación y desinstalación.
-   Licencias y avisos correspondientes.

------------------------------------------------------------------------

# 10. Documentación y presentación de GitHub

## 10.1. README

El README debería permitir que una persona entienda el producto en menos
de un minuto.

Estructura recomendada:

1.  Nombre y descripción.
2.  Capturas reales.
3.  Funcionalidades principales.
4.  Estado del proyecto.
5.  Plataformas soportadas.
6.  Instalación.
7.  Ejecución desde código fuente.
8.  Pruebas.
9.  Arquitectura.
10. Licencia.
11. Roadmap.
12. Contribución y reporte de errores.

Evitar afirmar que una funcionalidad está completa si solo existe
parcialmente o no ha sido validada.

## 10.2. Capturas y demostración

Crear capturas reales de:

-   Ventana principal.
-   Navegación por páginas.
-   Edición de texto.
-   Inserción de imágenes.
-   Redacción.
-   Exportación.
-   Comparación antes/después.

Añadir un GIF corto que muestre un flujo de trabajo completo.

No utilizar imágenes conceptuales como si fueran capturas de la
aplicación real.

## 10.3. Documentos complementarios

Crear o actualizar:

``` text
README.md
CHANGELOG.md
CONTRIBUTING.md
TESTING.md
SECURITY.md
LICENSE
docs/
├── architecture.md
├── export-workflow.md
├── redaction.md
├── coordinate-system.md
├── performance.md
└── user-guide.md
```

Ajustar los nombres a la documentación que ya exista; no duplicar
documentos equivalentes.

------------------------------------------------------------------------

# 11. Roadmap de implementación

La siguiente planificación es una propuesta por hitos, no una estimación
de duración garantizada.

## Hito 0 --- Auditoría del estado actual

-   [ ] Revisar estructura real del repositorio.
-   [ ] Identificar funcionalidades implementadas y pendientes.
-   [ ] Ejecutar todos los tests existentes.
-   [ ] Registrar fallos y advertencias.
-   [ ] Revisar dependencias y versiones.
-   [ ] Revisar CI y artefactos.
-   [ ] Contrastar README, PLAN y CHANGELOG.
-   [ ] Crear issues para hallazgos confirmados.

**Entregable:** informe de estado con defectos reproducibles y
prioridades.

## Hito 1 --- Integridad y seguridad documental

-   [ ] Revisar el flujo de exportación.
-   [ ] Comprobar protección del original.
-   [ ] Añadir pruebas de fallos de exportación.
-   [ ] Auditar redacción permanente.
-   [ ] Crear corpus de PDFs de prueba.
-   [ ] Verificar texto, imágenes y objetos afectados.
-   [ ] Revisar metadatos y adjuntos según el alcance definido.
-   [ ] Documentar limitaciones conocidas.

**Entregable:** suite de pruebas de integridad y redacción.

## Hito 2 --- Geometría y comandos

-   [ ] Centralizar transformaciones de coordenadas.
-   [ ] Añadir pruebas de ida y vuelta.
-   [ ] Cubrir rotaciones y distintos tamaños de página.
-   [ ] Revisar límites de selección.
-   [ ] Formalizar contratos de comandos.
-   [ ] Probar undo/redo con secuencias.
-   [ ] Verificar que operaciones fallidas no alteren el estado.

**Entregable:** edición geométricamente consistente y comandos
verificables.

## Hito 3 --- Rendimiento y estabilidad

-   [ ] Medir línea base de rendimiento.
-   [ ] Revisar tareas en segundo plano.
-   [ ] Revisar cancelación y cierre de trabajadores.
-   [ ] Implementar o ajustar caché LRU.
-   [ ] Añadir límites de recursos.
-   [ ] Ejecutar pruebas con documentos grandes.
-   [ ] Corregir bloqueos y fugas detectadas.

**Entregable:** informe de rendimiento y pruebas de estabilidad.

## Hito 4 --- UX y distribución

-   [ ] Mejorar estados y mensajes.
-   [ ] Añadir comparación antes/después.
-   [ ] Revisar accesibilidad.
-   [ ] Resolver estrategia de licenciamiento.
-   [ ] Validar empaquetado en máquina limpia.
-   [ ] Crear instalador si corresponde.
-   [ ] Preparar capturas y demostración.
-   [ ] Publicar una versión candidata.

**Entregable:** versión candidata instalable y documentada.

## Hito 5 --- Evolución funcional

-   [ ] OCR local.
-   [ ] Búsqueda avanzada.
-   [ ] Procesamiento por lotes.
-   [ ] Compresión.
-   [ ] Protección mediante contraseña.
-   [ ] Anotaciones.
-   [ ] Evaluación de firma digital.

**Entregable:** funcionalidades avanzadas integradas sin degradar
estabilidad.

------------------------------------------------------------------------

# 12. Definición de terminado (Definition of Done)

Una funcionalidad no debe marcarse como terminada únicamente porque
funciona en el caso feliz.

Se considera terminada cuando:

-   [ ] Cumple sus requisitos funcionales.
-   [ ] Respeta la arquitectura y los contratos existentes.
-   [ ] Maneja entradas inválidas.
-   [ ] Maneja errores de infraestructura.
-   [ ] No bloquea indebidamente la interfaz.
-   [ ] Tiene pruebas unitarias o de integración apropiadas.
-   [ ] No introduce regresiones.
-   [ ] Tiene documentación actualizada.
-   [ ] Sus limitaciones están documentadas.
-   [ ] Ha sido validada en los entornos que declara soportar.

Para operaciones destructivas o sensibles, se requiere además una
revisión específica de integridad y seguridad.

------------------------------------------------------------------------

# 13. Métricas de calidad

Registrar una línea base antes de establecer objetivos definitivos.

  Métrica                    Cómo medirla
  -------------------------- ---------------------------------
  Cobertura de pruebas       pytest-cov
  Errores estáticos          Ruff y Mypy
  Tiempo de apertura         Benchmark reproducible
  Tiempo de primera página   Medición automatizada
  Tiempo de exportación      Benchmark por perfil
  Memoria máxima             Medición del proceso
  Fallos de exportación      Suite de fallos inducidos
  Integridad de redacción    Corpus de PDFs y verificaciones
  Compatibilidad             Matriz de sistemas y versiones
  Tamaño de paquete          Artefacto de release

Publicar los resultados con versión de BenePDF, sistema operativo,
hardware, tamaño y características del documento de prueba.

------------------------------------------------------------------------

# 14. Orden recomendado de trabajo

Si el tiempo es limitado, seguir este orden:

1.  **No añadir funcionalidades nuevas todavía.**
2.  Auditar el código y ejecutar las pruebas actuales.
3.  Corregir fallos confirmados del flujo de exportación.
4.  Validar redacción permanente con documentos adversariales.
5.  Centralizar y probar transformaciones geométricas.
6.  Revisar undo/redo y consistencia de comandos.
7.  Medir rendimiento y consumo de memoria.
8.  Resolver licenciamiento.
9.  Validar el ejecutable en una máquina limpia.
10. Mejorar README, capturas y documentación.
11. Publicar una versión estable.
12. Empezar OCR, procesamiento por lotes y otras funcionalidades.

------------------------------------------------------------------------

# 15. Checklist de lanzamiento

## Calidad

-   [ ] Todas las pruebas obligatorias pasan.
-   [ ] Ruff y Mypy no presentan errores no justificados.
-   [ ] No existen defectos críticos abiertos.
-   [ ] Los documentos de prueba cubren escenarios normales y
    adversariales.

## Integridad

-   [ ] El original se conserva.
-   [ ] La exportación es validada.
-   [ ] La redacción se verifica estructural y visualmente.
-   [ ] Los errores no producen archivos finales incompletos.
-   [ ] Los temporales se gestionan correctamente.

## Experiencia

-   [ ] La interfaz no se bloquea durante operaciones costosas.
-   [ ] Los mensajes de error son comprensibles.
-   [ ] Los cambios pendientes son visibles.
-   [ ] Los flujos principales se pueden completar sin instrucciones de
    desarrollo.

## Distribución

-   [ ] Licenciamiento revisado.
-   [ ] Dependencias y avisos incluidos.
-   [ ] Instalación probada en entorno limpio.
-   [ ] Versionado y changelog actualizados.
-   [ ] Hashes de artefactos publicados.
-   [ ] Sistemas soportados declarados con precisión.

## Presentación

-   [ ] README actualizado.
-   [ ] Capturas reales.
-   [ ] Demostración breve.
-   [ ] Guía de instalación.
-   [ ] Guía de usuario.
-   [ ] Limitaciones conocidas documentadas.

------------------------------------------------------------------------

# 16. Recomendación final

La evolución más valiosa de BenePDF no consiste en acumular herramientas
de edición, sino en demostrar que puede manipular documentos importantes
sin perder información, introducir errores silenciosos ni comprometer la
privacidad del usuario.

La prioridad debe ser:

**Integridad documental → seguridad → geometría → estabilidad →
distribución → experiencia de usuario → funcionalidades avanzadas.**

Una versión estable, bien probada, instalable y documentada tendrá más
valor profesional que una versión con muchas funcionalidades cuya
fiabilidad no esté demostrada.

Este documento debe utilizarse como hoja de ruta viva: cada tarea debe
convertirse en un issue o pull request, vincularse a pruebas y cerrarse
únicamente cuando cumpla sus criterios de aceptación.

# GithubAction Error Calidad (ubuntu-latest)

21s
Run pytest
============================= test session starts ==============================
platform linux -- Python 3.12.16, pytest-9.2.0, pluggy-1.7.0
PySide6 6.12.0 -- Qt runtime 6.12.0 -- Qt compiled 6.12.0
rootdir: /home/runner/work/BenePDF/BenePDF
configfile: pyproject.toml
testpaths: tests
plugins: cov-7.1.0, qt-4.5.0
collected 607 items / 2 deselected / 605 selected

tests/integration/test_document_functions.py ....................        [  3%]
tests/integration/test_export.py ....................................... [  9%]
.................                                                        [ 12%]
tests/integration/test_pymupdf_engine.py ............................... [ 17%]
.....                                                                    [ 18%]
tests/ui/test_accessibility.py .........                                 [ 20%]
tests/ui/test_bootstrap.py ..                                            [ 20%]
tests/ui/test_document_functions_ui.py ..........................        [ 24%]
tests/ui/test_images.py .......                                          [ 25%]
tests/ui/test_main_window.py ..............................              [ 30%]
tests/ui/test_main_window_editing.py ........................            [ 34%]
tests/ui/test_main_window_export.py ............                         [ 36%]
tests/ui/test_main_window_thumbnails.py ....                             [ 37%]
tests/ui/test_pdf_canvas.py ..........                                   [ 39%]
tests/ui/test_pdf_canvas_editing.py ............................F..      [ 44%]
tests/ui/test_properties_panel.py ......                                 [ 45%]
tests/ui/test_render_scheduler.py ......                                 [ 46%]
tests/ui/test_smoke_editing.py ...                                       [ 46%]
tests/ui/test_text_dialog.py ....                                        [ 47%]
tests/ui/test_thumbnail_panel.py .....                                   [ 48%]
tests/ui/test_thumbnail_worker.py ....                                   [ 48%]
tests/unit/test_architecture.py .....                                    [ 49%]
tests/unit/test_build_app.py ........                                    [ 50%]
tests/unit/test_classification.py ................                       [ 53%]
tests/unit/test_config.py ......                                         [ 54%]
tests/unit/test_coordinates.py ...............................           [ 59%]
tests/unit/test_edit_history.py ....                                     [ 60%]
tests/unit/test_edit_session.py .....................                    [ 63%]
tests/unit/test_edit_session_pages.py ........................           [ 67%]
tests/unit/test_editing_models.py .............................          [ 72%]
tests/unit/test_errors.py .......                                        [ 73%]
tests/unit/test_export_document.py .........                             [ 75%]
tests/unit/test_fit.py ..........................                        [ 79%]
tests/unit/test_logging.py .......                                       [ 80%]
tests/unit/test_main.py ...                                              [ 81%]
tests/unit/test_models.py ..............................                 [ 86%]
tests/unit/test_open_document.py ........                                [ 87%]
tests/unit/test_package.py .                                             [ 87%]
tests/unit/test_pages.py .................................               [ 93%]
tests/unit/test_pdf_engine_port.py .............                         [ 95%]
tests/unit/test_render_cache.py .............                            [ 97%]
tests/unit/test_render_page.py ................                          [100%]

=================================== FAILURES ===================================
___________________ TestPintura.test_pinta_el_texto_anadido ____________________

self = <tests.ui.test_pdf_canvas_editing.TestPintura object at 0x7864c8464800>
qtbot = <pytestqt.qtbot.QtBot object at 0x7864c8499ac0>

    def test_pinta_el_texto_anadido(self, qtbot: QtBot) -> None:
        canvas = make_canvas(qtbot)
        canvas.set_objects([make_text()])
    
        pixmap = canvas.grab()
    
        colors = {
            pixmap.toImage().pixelColor(x, y).name() for x in range(15, 55) for y in range(25, 75)
        }
>       assert "#000000" in colors
E       AssertionError: assert '#000000' in {'#094699', '#0950a5', '#0c3c8d', '#0d50a5', '#0e50a5', '#0f4699', ...}

tests/ui/test_pdf_canvas_editing.py:494: AssertionError
=========================== short test summary info ============================
FAILED tests/ui/test_pdf_canvas_editing.py::TestPintura::test_pinta_el_texto_anadido - AssertionError: assert '#000000' in {'#094699', '#0950a5', '#0c3c8d', '#0d50a5', '#0e50a5', '#0f4699', ...}
================= 1 failed, 604 passed, 2 deselected in 20.07s =================
Error: Process completed with exit code 1.
