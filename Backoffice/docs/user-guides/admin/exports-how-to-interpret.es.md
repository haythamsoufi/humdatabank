# Exportaciones: cómo interpretar archivos (administrador)

Usa esta guía cuando hayas descargado una exportación (CSV/Excel) y quieras entender qué significan las columnas y cómo evitar errores comunes.

## Antes de comenzar

- El contenido de la exportación depende de la plantilla y tu flujo de trabajo.
- Si tu exportación admite "filtros" (estado, país, período), anota lo que seleccionaste para poder reproducirlo.

## Qué obtienes generalmente en una exportación

La mayoría de las exportaciones incluyen una mezcla de:

- **Columnas de metadatos** (contexto)
  - nombre de asignación / ID de asignación
  - país / organización
  - estado de envío
  - marcas de tiempo enviado/actualizado
  - enviado por (usuario)
- **Columnas de respuestas** (tus campos de plantilla)
  - una columna por campo, o múltiples columnas para campos complejos (como matrices)
- **Códigos/ID**
  - ID internos, códigos de indicadores o ID de preguntas que ayudan a unir conjuntos de datos de manera confiable

## Cómo generalmente se exportan los campos matriz/tabla

Las respuestas de matriz a menudo se convierten en múltiples columnas, por ejemplo:
- una columna por fila (si es una columna numérica única), o
- combinaciones fila × columna (si es una matriz de múltiples columnas)

Consejo: Mantén los encabezados de columna tal cual hasta que termines de limpiar tu conjunto de datos; renombrar demasiado temprano hace difícil comparar entre períodos.

## Cómo evitar errores de "exportación incorrecta"

### Confirma que exportaste el alcance correcto

Antes del análisis, confirma:
- el nombre de la asignación y el período son correctos
- la lista de países coincide con tu alcance previsto
- el filtro de estado coincide con tu intención (por ejemplo solo "Aprobado")

### Ten cuidado con los cambios de versión de plantilla

Si las versiones de plantilla cambiaron entre períodos, las exportaciones pueden diferir:
- aparecen nuevas columnas
- desaparecen columnas antiguas
- cambian los significados (peor caso)

Recomendación:
- Para cambios mayores, trátalo como un nuevo instrumento de reportes y documenta el cambio claramente.

## Enfoque de limpieza recomendado (simple y seguro)

1. **Mantén una copia sin procesar** de la exportación (no la edites).
2. Haz una copia de trabajo y agrega tus pasos de limpieza allí.
3. Mantén ID/códigos:
   - ayudan con fusiones y deduplicación
4. Si necesitas una sola fila "país-período", decide cómo manejarás:
   - múltiples envíos
   - entradas reabiertas/re-enviadas

## Problemas comunes

- **La exportación falta un país**: el país puede no estar incluido en la asignación, no ha enviado, o necesitas exportarlo por separado desde la página del formulario de entrada.
- **Los números no coinciden con el formulario**: verifica la versión de plantilla/período y si se aplica redondeo o formato.
- **Filas duplicadas**: exportaste múltiples estados (borrador + enviado + aprobado) o existen múltiples envíos.
- **La exportación tarda demasiado**: exporta alcances más pequeños (una asignación a la vez).

## Relacionado

- [Exportar y descargar datos](export-download-data.md)
- [Ejecutar un ciclo de reportes](run-a-reporting-cycle.md)
- [Estados de envío y qué puedes hacer](../common/submission-statuses-and-permissions.md)
