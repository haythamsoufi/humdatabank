---
id: manage-assignments
title: Gestionar asignaciones
description: Guía para ver, editar y gestionar asignaciones de formularios existentes
roles: [admin]
category: assignment-management
keywords: [editar asignación, ver asignaciones, monitorear progreso, extender fecha límite, eliminar asignación, estado asignación]
pages:
  - /admin/assignments
  - /admin/assignments/edit
---

# Gestionar asignaciones

Este flujo de trabajo guía a los administradores a través de ver, editar y gestionar asignaciones de formularios existentes a países y puntos focales.

## Prerrequisitos

- Se requiere rol de administrador
- Al menos una asignación existente en el sistema

## Pasos

### Paso 1: Navegar a la gestión de asignaciones
- **Página**: `/admin/assignments`
- **Selector**: `.assignments-list, [data-testid="assignments-grid"]`
- **Acción**: Ver la lista de todas las asignaciones
- **Ayuda**: La página Asignaciones muestra todas las asignaciones actuales y pasadas. Puedes ver el nombre del período, plantilla, estado de envío y estado de URL pública de cada asignación.
- **Texto de acción**: Siguiente

### Paso 2: Ver detalles de la asignación
- **Página**: `/admin/assignments`
- **Selector**: `.assignment-row, [data-assignment-id]`
- **Acción**: Revisa la información de la asignación
- **Ayuda**: Cada fila de asignación muestra el nombre del período, nombre de la plantilla y progreso de envío. Usa esto para identificar qué asignaciones necesitan atención.
- **Texto de acción**: Siguiente

### Paso 3: Monitorear progreso de envío
- **Página**: `/admin/assignments`
- **Selector**: `.progress-indicator, .submission-status`
- **Acción**: Verifica el estado de finalización
- **Ayuda**: Ve qué países han enviado, cuáles están en progreso y cuáles están vencidos. Esto te ayuda a identificar dónde se necesita seguimiento.
- **Texto de acción**: Siguiente

## Editar una asignación

### Paso 1: Abrir formulario de edición
- **Página**: `/admin/assignments`
- **Selector**: `a[href*="/admin/assignments/edit"], .edit-assignment-btn`
- **Acción**: Haz clic en el icono de edición junto a la asignación
- **Ayuda**: Haz clic en el icono de edición (lápiz) junto a la asignación que quieres modificar. Esto abre el formulario de edición de asignación.
- **Texto de acción**: Continuar

### Paso 2: Actualizar detalles de la asignación
- **Página**: `/admin/assignments/edit/<assignment_id>`
- **Selector**: `#assignment-details-panel, form`
- **Acción**: Modifica la información de la asignación
- **Ayuda**: Puedes actualizar la plantilla, nombre del período y fecha límite. Los cambios en la fecha límite se aplicarán a todos los países en la asignación.
- **Campos**:
  - Plantilla: Cambia la plantilla del formulario (si es necesario)
  - Nombre del período: Actualiza el nombre de la asignación
  - Fecha límite: Extiende o modifica la fecha límite de envío

### Paso 3: Agregar países a la asignación
- **Página**: `/admin/assignments/edit/<assignment_id>`
- **Selector**: `.add-countries-section, #add-countries-btn`
- **Acción**: Agrega países adicionales
- **Ayuda**: Si necesitas agregar más países a una asignación existente, usa la sección "Agregar países". Selecciona países y haz clic en "Agregar" para incluirlos.
- **Texto de acción**: Siguiente

### Paso 4: Guardar cambios
- **Página**: `/admin/assignments/edit/<assignment_id>`
- **Selector**: `button[type="submit"], .save-btn`
- **Acción**: Haz clic en Guardar cambios
- **Ayuda**: Haz clic en "Guardar cambios" para aplicar tus actualizaciones. Los puntos focales serán notificados si se agregan nuevos países.
- **Texto de acción**: Entendido

## Gestionar URL públicas

### Ver estado de URL pública
- **Página**: `/admin/assignments`
- **Selector**: `.public-url-status, [data-public-url]`
- **Acción**: Verifica si la asignación tiene URL pública
- **Ayuda**: La lista de asignaciones muestra si cada asignación tiene una URL pública habilitada. Las URL públicas permiten envíos sin inicio de sesión.

### Generar URL pública
- **Página**: `/admin/assignments`
- **Selector**: `.generate-public-url-btn, [data-action="generate-url"]`
- **Acción**: Haz clic en "Generar URL pública"
- **Ayuda**: Si una asignación no tiene una URL pública, puedes generar una. Esto permite envíos públicos sin requerir inicio de sesión.

### Cambiar estado de URL pública
- **Página**: `/admin/assignments`
- **Selector**: `.toggle-public-url, [data-action="toggle-public"]`
- **Acción**: Activa o desactiva la URL pública
- **Ayuda**: Activa o desactiva la URL pública. Cuando está activa, la URL pública es accesible. Cuando está inactiva, los envíos están deshabilitados.

### Copiar URL pública
- **Página**: `/admin/assignments`
- **Selector**: `.copy-url-btn, [data-action="copy-url"]`
- **Acción**: Haz clic para copiar URL
- **Ayuda**: Copia la URL pública para compartirla con usuarios externos que necesitan enviar datos sin iniciar sesión.

## Ver envíos públicos

### Ver todos los envíos públicos
- **Página**: `/admin/assignments`
- **Selector**: `a[href="/admin/assignments/public-submissions"], .view-public-submissions-btn`
- **Acción**: Haz clic en "Ver todos los envíos públicos"
- **Ayuda**: Ve todos los envíos públicos en todas las asignaciones. Esto te ayuda a monitorear envíos externos.

### Ver envíos específicos de asignación
- **Página**: `/admin/assignments`
- **Selector**: `.view-submissions-btn, [data-action="view-submissions"]`
- **Acción**: Haz clic en "Ver envíos" para una asignación específica
- **Ayuda**: Ve y gestiona envíos públicos para una asignación específica. Puedes aprobar, rechazar o revisar envíos.

## Eliminar una asignación

### Paso 1: Confirmar eliminación
- **Página**: `/admin/assignments`
- **Selector**: `.delete-assignment-btn, [data-action="delete"]`
- **Acción**: Haz clic en el icono de eliminar
- **Ayuda**: Haz clic en el icono de eliminar (papelera) junto a la asignación que quieres eliminar. Se te pedirá que confirmes.

### Paso 2: Confirmar eliminación
- **Página**: `/admin/assignments`
- **Selector**: `.confirm-delete-btn, [data-confirm="delete"]`
- **Acción**: Confirma la eliminación
- **Ayuda**: Confirma que quieres eliminar la asignación. Esto eliminará la asignación y todos los estados de países y datos asociados. Esta acción no se puede deshacer.
- **Texto de acción**: Entendido

## Vista de línea de tiempo

### Acceder al diagrama de Gantt
- **Página**: `/admin/assignments`
- **Selector**: `a[href="/admin/assignments/gantt"], .timeline-view-btn`
- **Acción**: Haz clic en "Vista de línea de tiempo"
- **Ayuda**: Ve todas las asignaciones en un gráfico de línea de tiempo/Gantt. Esto ayuda a visualizar fechas límite y asignaciones superpuestas.

## Consejos

- Monitorea el panel de control regularmente para envíos vencidos
- Usa la vista de línea de tiempo para evitar conflictos de programación
- Extiende las fechas límite de manera proactiva si muchos países tienen dificultades
- Las URL públicas son útiles para la recopilación de datos externos pero requieren monitoreo
- Revisa los envíos públicos regularmente para asegurar la calidad de los datos
- Considera enviar recordatorios antes de que se acerquen las fechas límite

## Flujos de trabajo relacionados

- [Crear nueva asignación](create-assignment.md) - Crear una nueva asignación
- [Crear plantilla](create-template.md) - Diseñar formularios antes de asignar
- [Ver asignaciones](../focal-point/view-assignments.md) - Perspectiva del punto focal
