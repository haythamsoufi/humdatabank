---
id: create-template
title: Crear plantilla de formulario
description: Guía para crear una nueva plantilla de formulario con secciones y campos
roles: [admin]
category: template-management
keywords: [nueva plantilla, generador de formularios, crear formulario, diseñar formulario, construir plantilla]
pages:
  - /admin/templates
  - /admin/templates/new
---

# Crear plantilla de formulario

Este flujo de trabajo guía a los administradores a través de la creación de una nueva plantilla de formulario usando el generador de formularios.

## Prerrequisitos

- Se requiere rol de administrador
- Acceso a la sección Gestión de formularios y datos
- Comprensión de los datos que quieres recopilar

## Pasos

### Paso 1: Navegar a la gestión de plantillas
- **Página**: `/admin/templates`
- **Selector**: `a[href="/admin/templates/new"], .create-template-btn`
- **Acción**: Haz clic en "Crear plantilla"
- **Ayuda**: Haz clic en el botón "Crear plantilla" para comenzar a construir una nueva plantilla de formulario.
- **Texto de acción**: Continuar

### Paso 2: Establecer detalles de la plantilla
- **Página**: `/admin/templates/new`
- **Selector**: `#template-details, .template-info-panel`
- **Acción**: Ingresa el nombre y descripción de la plantilla
- **Ayuda**: Dale a tu plantilla un nombre claro y descriptivo y agrega una descripción explicando su propósito. Esto ayuda a los usuarios a entender para qué es el formulario.
- **Campos**:
  - Nombre de la plantilla (requerido): Nombre claro y descriptivo
  - Descripción: Explica el propósito de la plantilla
  - Acceso a la plantilla: Elige quién puede ver/editar esta plantilla (propietario y administradores compartidos)

### Paso 3: Agregar secciones
- **Página**: `/admin/templates/new`
- **Selector**: `.add-section-btn, [data-action="add-section"]`
- **Acción**: Haz clic en "Agregar sección"
- **Ayuda**: Las secciones organizan tu formulario en grupos lógicos. Agrega una sección para cada tema o categoría de preguntas.
- **Texto de acción**: Siguiente

### Paso 4: Configurar sección
- **Página**: `/admin/templates/new`
- **Selector**: `.section-config, .section-panel`
- **Acción**: Nombra la sección y configura los ajustes
- **Ayuda**: Dale a cada sección un título y descripción opcional. También puedes establecer condiciones de visibilidad y permisos.
- **Campos**:
  - Título de la sección (requerido): Nombre para esta sección
  - Descripción: Instrucciones opcionales para usuarios
  - Repliegue: Si los usuarios pueden colapsar la sección

### Paso 5: Agregar elementos de formulario
- **Página**: `/admin/templates/new`
- **Selector**: `.add-item-btn, [data-action="add-item"]`
- **Acción**: Agrega campos a la sección
- **Ayuda**: Agrega elementos de formulario como campos de texto, números, listas desplegables y más. Vincula elementos a indicadores del Banco de indicadores para recopilación de datos estandarizada.
- **Texto de acción**: Siguiente

### Paso 6: Configurar elementos de formulario
- **Página**: `/admin/templates/new`
- **Selector**: `.item-config, .form-item-panel`
- **Acción**: Configura cada elemento de formulario
- **Ayuda**: Establece la etiqueta, tipo de campo, reglas de validación y vincula a un indicador si aplica. Los campos requeridos deben ser completados por los usuarios.
- **Campos**:
  - Etiqueta (requerido): Pregunta o etiqueta de campo
  - Tipo de campo: Texto, Número, Fecha, Lista desplegable, etc.
  - Requerido: Si este campo debe ser completado
  - Indicador: Vínculo al Banco de indicadores para estandarización

### Paso 7: Vista previa y guardar
- **Página**: `/admin/templates/new`
- **Selector**: `button[type="submit"], .save-template-btn`
- **Acción**: Guarda la plantilla
- **Ayuda**: Revisa la estructura de tu plantilla en la vista previa, luego haz clic en "Guardar plantilla" para crearla. Puedes editar la plantilla más tarde si es necesario.
- **Texto de acción**: Entendido

## Consejos

- Usa el Banco de indicadores para vincular campos a indicadores estandarizados
- Agrupa preguntas relacionadas en secciones para mejor organización
- Agrega descripciones para ayudar a los usuarios a entender qué ingresar
- Prueba la plantilla creando una asignación de prueba antes de desplegar
- Las plantillas se pueden duplicar para crear variaciones

## Flujos de trabajo relacionados

- [Gestionar asignaciones](manage-assignments.md) - Asignar plantillas a países
