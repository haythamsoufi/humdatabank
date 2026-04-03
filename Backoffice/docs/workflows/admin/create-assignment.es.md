---
id: create-assignment
title: Crear nueva asignación
description: Guía para crear una nueva asignación de formulario para distribuir plantillas a países
roles: [admin]
category: assignment-management
keywords: [crear asignación, asignar formulario, distribuir, tarea, fecha límite, asignación país, nueva asignación]
pages:
  - /admin/assignments
  - /admin/assignments/new
---

# Crear nueva asignación

Este flujo de trabajo guía a los administradores a través de la creación de una nueva asignación de formulario para distribuir plantillas a países y puntos focales.

## Prerrequisitos

- Se requiere rol de administrador
- Al menos una plantilla de formulario activa con una versión publicada
- Países configurados en el sistema

## Pasos

### Paso 1: Navegar a la gestión de asignaciones
- **Página**: `/admin/assignments`
- **Selector**: `a[href="/admin/assignments/new"], .create-assignment-btn`
- **Acción**: Haz clic en "Crear asignación"
- **Ayuda**: La página Asignaciones muestra todas las asignaciones actuales y pasadas. Haz clic en "Crear asignación" para distribuir un formulario a países.
- **Texto de acción**: Continuar

### Paso 2: Seleccionar plantilla
- **Página**: `/admin/assignments/new`
- **Selector**: `#template-select, select[name="template"]`
- **Acción**: Elige la plantilla de formulario a asignar
- **Ayuda**: Selecciona qué plantilla de formulario quieres distribuir. Solo aparecen plantillas activas con versiones publicadas en esta lista.
- **Texto de acción**: Siguiente

### Paso 3: Seleccionar países
- **Página**: `/admin/assignments/new`
- **Selector**: `#country-select, .country-selection`
- **Acción**: Elige países para recibir la asignación
- **Ayuda**: Selecciona uno o más países para recibir esta asignación. Puedes seleccionar todos los países o elegir específicos.
- **Texto de acción**: Siguiente

### Paso 4: Establecer nombre de período
- **Página**: `/admin/assignments/new`
- **Selector**: `#period-name, input[name="period_name"]`
- **Acción**: Ingresa un nombre de período para esta asignación
- **Ayuda**: Dale a esta asignación un nombre de período descriptivo (por ejemplo, "Recopilación de datos T1 2024" o "Informe anual 2024"). Esto ayuda a identificar la asignación más tarde.
- **Texto de acción**: Siguiente

### Paso 5: Establecer fecha límite
- **Página**: `/admin/assignments/new`
- **Selector**: `#deadline-input, input[type="date"], .deadline-picker`
- **Acción**: Establece la fecha límite de envío
- **Ayuda**: Elige una fecha límite para el envío de datos. Los puntos focales verán esta fecha límite y recibirán recordatorios a medida que se acerque.
- **Campos**:
  - Fecha límite (requerido): Cuándo vencen los envíos
  - Configuración de recordatorios: Configura recordatorios automáticos

### Paso 6: Agregar instrucciones
- **Página**: `/admin/assignments/new`
- **Selector**: `#instructions, textarea[name="instructions"]`
- **Acción**: Agrega instrucciones específicas de la asignación
- **Ayuda**: Proporciona cualquier instrucción especial o contexto para esta asignación. Este mensaje se mostrará a los puntos focales.
- **Texto de acción**: Siguiente

### Paso 7: Configurar URL pública (Opcional)
- **Página**: `/admin/assignments/new`
- **Selector**: `#generate-public-url, input[name="generate_public_url"]`
- **Acción**: Habilita URL pública si es necesario
- **Ayuda**: Si quieres permitir envíos públicos sin inicio de sesión, marca esta opción. Puedes activar o desactivar la URL pública más tarde.
- **Texto de acción**: Siguiente

### Paso 8: Revisar y crear
- **Página**: `/admin/assignments/new`
- **Selector**: `button[type="submit"], .create-btn`
- **Acción**: Crea la asignación
- **Ayuda**: Revisa los detalles de la asignación y haz clic en "Crear asignación". Los puntos focales serán notificados y verán la nueva tarea en su panel de control.
- **Texto de acción**: Entendido

## Consejos

- Establece fechas límite realistas considerando zonas horarias y días festivos
- Usa instrucciones claras y específicas en los mensajes de asignación
- Elige un nombre de período descriptivo que facilite identificar la asignación más tarde
- Solo las plantillas con versiones publicadas pueden ser asignadas
- Puedes agregar más países a una asignación después de la creación editándola

## Flujos de trabajo relacionados

- [Gestionar asignaciones](manage-assignments.md) - Ver, editar y gestionar asignaciones existentes
- [Crear plantilla](create-template.md) - Diseñar formularios antes de asignar
- [Ver asignaciones](../focal-point/view-assignments.md) - Perspectiva del punto focal
