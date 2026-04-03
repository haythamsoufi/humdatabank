# Generador de formularios (avanzado): tipos de campos, validación y cambios seguros

Usa esta guía cuando necesites diseñar plantillas que sean consistentes entre países y fáciles de enviar.

## Antes de comenzar

- Necesitas acceso de **Administrador** con permisos de plantilla.
- Si la plantilla ya se usa en asignaciones activas, prefiere **cambios pequeños y seguros** y prueba cuidadosamente.

## Cómo elegir el tipo de campo correcto

### Texto

Usa para nombres, descripciones cortas y respuestas "explica por qué".

Buenos ejemplos:
- "Describe el desafío principal (1-2 oraciones)"

Evita:
- Usar texto para números ("10") o fechas ("Ene 2026") cuando puedas usar un campo estructurado.

### Número

Usa para conteos, totales y cantidades.

Buenos ejemplos:
- "Total de voluntarios (número)"
- "Presupuesto (moneda local)"

Consejos:
- Decide de antemano si aceptas decimales.
- Sé explícito sobre las unidades en la etiqueta (por ejemplo "(personas)", "(CHF)").

### Fecha

Usa cuando el valor es una fecha, no un comentario.

Consejos:
- Si necesitas un período (inicio/fin), usa dos campos de fecha con etiquetas claras.

### Elección única (lista desplegable / botón de opción)

Usa cuando las respuestas deben ser consistentes entre países.

Consejos:
- Mantén las etiquetas de opciones cortas.
- Evita significados superpuestos (por ejemplo "Parcialmente" vs "Algo").

### Selección múltiple

Usa cuando pueden aplicarse múltiples opciones.

Consejos:
- Agrega una opción "Otro (especificar)" solo si realmente la necesitas, y combínala con un campo de texto.

### Matriz / tabla (filas repetidas)

Usa cuando la misma medida se recopila entre múltiples categorías (filas).

Buen ejemplo:
- Filas: "Mujeres", "Hombres", "Niñas", "Niños"
- Columnas: "Personas alcanzadas"

Mejores prácticas:
- Mantén la matriz pequeña (los usuarios tienen dificultades con tablas muy anchas).
- Asegúrate de que cada etiqueta de fila sea inequívoca.
- Prefiere campos numéricos dentro de matrices cuando esperas totales y validación.

## Validación y campos requeridos (qué bloquea el envío)

### Campos requeridos

Marca un campo como **requerido** solo cuando no puedes aceptar un envío sin él.

Si los usuarios frecuentemente se bloquean en **Enviar**:
- Reduce campos requeridos, especialmente en formularios largos.
- Agrega texto de ayuda para explicar cómo se ve "suficientemente bueno".

### Reglas de validación comunes (cuando están disponibles)

Si tu Generador de formularios las admite, usa reglas de validación para prevenir errores comunes:
- Número mínimo/máximo (por ejemplo "debe ser ≥ 0")
- Formatos permitidos (por ejemplo año)
- Celdas de matriz requeridas (solo cuando sea necesario)

Consejo: Si las reglas de validación son estrictas, los usuarios necesitarán etiquetas y ejemplos más claros.

## Lógica condicional (cuándo usarla)

Si tu Generador de formularios admite visualización condicional (mostrar/ocultar campos):
- Úsalo para reducir el desorden (haz preguntas de seguimiento solo cuando sea necesario).
- Evita árboles de ramificación profundos; son difíciles de probar y fáciles de romper.

Siempre agrega texto de ayuda en la pregunta "padre" para que los usuarios entiendan por qué aparecen los seguimientos.

## Versionado de plantilla y cambios "seguros vs riesgosos"

### Cambios seguros (generalmente OK durante una recopilación en vivo)

- Corrige errores tipográficos y redacción en etiquetas/texto de ayuda
- Reordena secciones/campos (cuando no cambia el significado)
- Agrega un nuevo campo opcional

### Cambios riesgosos (pueden romper comparaciones o confundir usuarios)

- Cambia un tipo de campo (texto → número, lista desplegable → selección múltiple)
- Cambia el significado de una pregunta pero mantén la misma etiqueta
- Elimina campos (puede eliminar contexto histórico)
- Cambia reglas requeridas a mitad de la recopilación

Enfoque recomendado para cambios riesgosos:
1. Crea un nuevo borrador/versión (si está admitido).
2. Prueba en una pequeña asignación (un país).
3. Despliega mediante una nueva asignación (preferido) y comunica el cambio.

## Vinculación al Banco de indicadores (reglas prácticas)

Vincula una pregunta a un indicador cuando necesites:
- definiciones estandarizadas
- reportes consistentes entre países

Evita:
- Vincular diferentes preguntas al mismo indicador a menos que realmente representen la misma medida.
- Forzar nombres técnicos de indicadores en etiquetas orientadas al usuario (mantén las etiquetas legibles por humanos).

## Plan de prueba (lista de verificación rápida)

Antes de publicar/usar una plantilla:
- Completa el formulario tú mismo como punto focal.
- Confirma que los campos requeridos son razonables.
- Intenta enviar con errores intencionales (requerido faltante, formatos incorrectos).
- Exporta un envío de prueba y confirma que las columnas de datos tienen sentido.

## Problemas comunes

- **Los puntos focales no pueden enviar**: demasiados campos requeridos o validación estricta; agrega texto de ayuda y reduce los requeridos.
- **Los datos son inconsistentes entre países**: las opciones de lista desplegable no son claras; ajusta las definiciones y vincula a indicadores donde sea apropiado.
- **Se usa la versión incorrecta de plantilla**: las asignaciones pueden estar vinculadas a versiones más antiguas; crea una nueva asignación al desplegar cambios mayores.

## Relacionado

- [Editar una plantilla (Generador de formularios)](edit-template.md)
- [Crear una plantilla de formulario](create-template.md)
- [Ciclo de vida de una asignación](assignment-lifecycle.md)
- [Solución de problemas (Punto focal)](../focal-point/troubleshooting.md)
