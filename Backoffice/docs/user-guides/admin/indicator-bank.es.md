# Banco de indicadores (guía de administrador)

Usa esta guía si gestionas definiciones de indicadores estándar y quieres reportes consistentes entre plantillas y asignaciones.

## Qué es el Banco de indicadores

El **Banco de indicadores** es una biblioteca de indicadores estandarizados (nombres, definiciones y a veces reglas de cálculo). Vincular campos de formulario a indicadores ayuda a mantener los datos consistentes entre:

- países
- períodos de tiempo
- diferentes plantillas

## Cuándo vincular un campo a un indicador

Vincula un campo de formulario a un indicador cuando:

- quieres que la misma medida se reporte de la misma manera en todas partes
- planeas exportar y comparar datos entre países/períodos
- quieres una definición estable que no cambie con la redacción local

No vincules cuando:

- el campo es texto puramente operativo (notas, explicaciones de forma libre)
- la pregunta es temporal o específica de una asignación

## Buenas prácticas

- Mantén las definiciones de indicadores estables con el tiempo.
- Si debes cambiar el significado, crea un nuevo indicador en lugar de "reutilizar" el antiguo.
- Usa unidades consistentes (personas, hogares, porcentaje, etc.).
- Haz que las etiquetas de campos sean fáciles de usar incluso si los nombres de indicadores son técnicos.

## Solución de problemas

- **Las exportaciones parecen inconsistentes**: confirma que las plantillas están vinculadas a los indicadores correctos y que las definiciones de indicadores no cambiaron a mitad del período.
- **Múltiples campos vinculados al mismo indicador**: verifica si representan la misma medida; si no, divídelos en indicadores separados.

## Relacionado

- [Crear plantilla de formulario](create-template.md)
- [Editar una plantilla de formulario (Generador de formularios)](edit-template.md)
