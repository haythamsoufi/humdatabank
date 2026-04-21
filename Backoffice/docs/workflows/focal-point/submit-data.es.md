---
id: submit-data
title: Enviar datos de formulario
description: Guía para puntos focales para completar y enviar datos de formulario
roles: [focal_point, admin]
category: data-entry
keywords: [completar formulario, ingresar datos, enviar, completar asignación, entrada de datos]
pages:
  - /
  - /forms/assignment
---

# Enviar datos de formulario

Este flujo de trabajo guía a los puntos focales a través de completar y enviar datos de formulario para sus asignaciones.

## Prerrequisitos

- Se requiere rol de punto focal
- Una asignación activa para tu país
- Datos listos para ingresar

## Pasos

### Paso 1: Encontrar tu asignación en el panel de control
- **Página**: `/`
- **Selector**: `.bg-white.p-6.rounded-lg.shadow-md, .grid.gap-4`
- **Acción**: Localiza tu formulario asignado
- **Ayuda**: Tu panel de control muestra todos los formularios asignados a ti. Busca formularios con estado "En progreso" o "No iniciado". Haz clic en un formulario para comenzar a ingresar datos.
- **Texto de acción**: Continuar

### Paso 2: Abrir el formulario de entrada de datos
- **Página**: `/`
- **Selector**: `a[href*="/forms/assignment/"], a[href*="view_edit_form"], .p-4.rounded-lg.shadow-md a`
- **Acción**: Haz clic para abrir el formulario
- **Ayuda**: Haz clic en el título de la asignación (resaltado arriba) para abrir el formulario de entrada de datos. El recorrido continuará en la página del formulario.
- **Texto de acción**: Haz clic en una asignación

### Paso 3: Navegar secciones del formulario
- **Página**: `/forms/assignment`
- **Selector**: `#section-navigation-sidebar, .section-link`
- **Acción**: Ver secciones disponibles
- **Ayuda**: El formulario está organizado en secciones mostradas en la barra lateral izquierda. Haz clic en un nombre de sección para saltar a ella. Cada sección muestra un indicador de finalización.
- **Texto de acción**: Siguiente

### Paso 4: Completar campos requeridos
- **Página**: `/forms/assignment`
- **Selector**: `#main-form-area, #sections-container`
- **Acción**: Ingresa tus datos
- **Ayuda**: Completa cada campo con los datos apropiados. Los campos requeridos están marcados con un asterisco (*). Tus cambios se guardan automáticamente mientras trabajas.
- **Texto de acción**: Siguiente

### Paso 5: Enviar el formulario
- **Página**: `/forms/assignment`
- **Selector**: `button[value="submit"], #fab-submit-btn, button.bg-green-600`
- **Acción**: Haz clic en Enviar
- **Ayuda**: Una vez que todos los campos requeridos estén completos, haz clic en el botón verde Enviar para finalizar tus datos. En móvil, usa el botón de acción flotante. Recibirás un mensaje de confirmación.
- **Texto de acción**: Entendido

## Guardar tu progreso

- Tus datos se guardan automáticamente mientras trabajas
- Puedes salir y volver en cualquier momento
- Busca el indicador "Último guardado" para confirmar guardados
- Usa "Guardar borrador" para guardar explícitamente tu progreso actual

## Consejos

- Reúne todos tus datos antes de comenzar para evitar interrupciones
- Usa los campos de comentarios para documentar fuentes de datos
- Verifica los mensajes de validación cuidadosamente antes de enviar
- Puedes editar datos enviados si tu administrador lo permite
- Exporta tu envío como PDF para tus registros

## Flujos de trabajo relacionados

- [Ver asignaciones](view-assignments.md) - Ver todas tus tareas pendientes
