# Solución de problemas de plantillas y asignaciones (administrador)

Usa esta guía cuando algo parece incorrecto con plantillas/asignaciones (versión incorrecta, países faltantes, envíos bloqueados, exportaciones confusas).

## Problemas de plantilla

### "Mis cambios en la plantilla no aparecen para los puntos focales"

Causas comunes:
- editaste un borrador pero no lo publicaste (si la publicación existe en tu configuración)
- la asignación está vinculada a una plantilla/versión más antigua

Qué hacer:
- Confirma qué plantilla/versión usa la asignación.
- Para cambios mayores, crea una nueva asignación y comunica el cambio.

### "Los usuarios no pueden enviar después de actualizar la plantilla"

Causas comunes:
- se agregaron nuevos campos requeridos
- las reglas de validación son demasiado estrictas
- una matriz/tabla tiene celdas requeridas

Qué hacer:
- Prueba como punto focal en una pequeña asignación.
- Reduce campos requeridos y agrega texto de ayuda más claro.

Ver: [Generador de formularios (avanzado)](form-builder-advanced.md)

## Problemas de asignación

### "Falta un país de la asignación"

Causas comunes:
- el país no fue seleccionado durante la creación
- el país fue eliminado más tarde
- el país está filtrado por configuraciones de estado/vista

Qué hacer:
- Verifica la configuración de la asignación y agrega el país si es necesario.
- Confirma que los puntos focales para ese país tienen acceso al país.

### "Un punto focal dice que no puede ver la asignación"

Razones más comunes:
- falta rol de asignación (entrada de datos/vista)
- falta acceso al país
- la asignación no está activa para ese período

Verificaciones iniciales:
- confirma los roles del usuario (ver [Roles y permisos de usuario](user-roles.md))
- confirma el acceso al país del usuario
- confirma que la asignación incluye ese país

### "Necesitamos corregir datos después del envío"

Enfoques típicos:
- Reabrir/devolver el envío (si tu flujo de trabajo lo admite)
- Pide al punto focal que corrija y re-envíe

Ver: [Revisar y aprobar envíos](review-approve-submissions.md) y [Estados de envío y qué puedes hacer](../common/submission-statuses-and-permissions.md)

## Problemas de exportación

### "La exportación falta datos o tiene columnas inesperadas"

Causas comunes:
- exportando la asignación/período incorrecto
- versión de plantilla cambiada
- filtro de exportación excluyó ciertos estados/países

Ver: [Exportaciones: cómo interpretar archivos](exports-how-to-interpret.md)

## Relacionado

- [Ciclo de vida de una asignación](assignment-lifecycle.md)
- [Gestionar asignaciones](manage-assignments.md)
- [Generador de formularios (avanzado)](form-builder-advanced.md)
