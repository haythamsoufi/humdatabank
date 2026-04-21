---
id: view-assignments
title: Ver tus asignaciones
description: Guía para puntos focales para ver y gestionar sus asignaciones pendientes
roles: [focal_point, admin]
category: data-entry
keywords: [mis tareas, pendiente, fecha límite, asignaciones, panel de control, por hacer]
pages:
  - /
---

# Ver tus asignaciones

Este flujo de trabajo guía a los puntos focales a través de ver sus asignaciones pendientes y entender sus tareas.

## Prerrequisitos

- Se requiere rol de punto focal
- Asignado a al menos un país

## Pasos

### Paso 1: Acceder a tu panel de control
- **Página**: `/`
- **Selector**: `.bg-white.p-6.rounded-lg.shadow-md, .grid.gap-4`
- **Acción**: Ver tu panel de control
- **Ayuda**: Tu panel de control muestra todas tus asignaciones pendientes. Cada tarjeta muestra el nombre del formulario, fecha de vencimiento, estado de finalización y porcentaje de progreso.
- **Texto de acción**: Siguiente

### Paso 2: Revisar tarjetas de asignación
- **Página**: `/`
- **Selector**: `.p-4.rounded-lg.shadow-md, .bg-gray-50.border`
- **Acción**: Revisa cada asignación
- **Ayuda**: Cada tarjeta de asignación muestra el nombre de la plantilla, período, fecha de vencimiento y estado actual. Las asignaciones vencidas tienen un borde rojo y una insignia "Vencido".
- **Texto de acción**: Siguiente

### Paso 3: Abrir una asignación
- **Página**: `/`
- **Selector**: `a[href*="/forms/assignment/"], .p-4.rounded-lg a`
- **Acción**: Haz clic para abrir el formulario
- **Ayuda**: Haz clic en el título de la asignación para abrir el formulario de entrada de datos. Puedes ver el porcentaje de finalización y el estado antes de hacer clic.
- **Texto de acción**: Haz clic en una asignación

## Entender el estado de la asignación

| Estado | Significado |
|--------|-------------|
| **Pendiente** | Aún no iniciado |
| **En progreso** | Iniciado pero no enviado |
| **Enviado** | Completado y enviado |
| **Vencido** | Pasada la fecha límite, no enviado |

## Consejos

- Verifica tu panel de control regularmente para nuevas asignaciones
- Comienza temprano para evitar problemas de último minuto
- Tu progreso se guarda automáticamente mientras trabajas
- Puedes contactar a tu administrador si tienes preguntas sobre una asignación
- Usa el panel de notificaciones para ver actualizaciones recientes

## Flujos de trabajo relacionados

- [Enviar datos](submit-data.md) - Completar y enviar un formulario
