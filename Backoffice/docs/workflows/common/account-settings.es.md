---
id: account-settings
title: Gestionar configuración de cuenta
description: Guía para actualizar tu perfil, contraseña y preferencias
roles: [admin, focal_point]
category: account
keywords: [perfil, contraseña, configuración, preferencias, cambiar contraseña, actualizar perfil]
pages:
  - /account-settings
---

# Gestionar configuración de cuenta

Este flujo de trabajo te guía a través de la actualización de tu configuración de cuenta, información de perfil y contraseña.

## Prerrequisitos

- Iniciado sesión en el sistema

## Pasos

### Paso 1: Navegar a la configuración de cuenta
- **Página**: `/account-settings`
- **Selector**: `.bg-white.p-6.rounded-lg.shadow-md`
- **Acción**: Accede a tu configuración de cuenta
- **Ayuda**: Esta es tu página de configuración de cuenta donde puedes actualizar tu información personal, preferencias y contraseña.
- **Texto de acción**: Siguiente

### Paso 2: Actualizar información personal
- **Página**: `/account-settings`
- **Selector**: `input[name="name"], input[name="phone"], #profile_color`
- **Acción**: Edita tus detalles de perfil
- **Ayuda**: Actualiza tu nombre para mostrar, número de teléfono y color de perfil. Tu dirección de correo electrónico no se puede cambiar - es tu ID de inicio de sesión.
- **Texto de acción**: Siguiente

### Paso 3: Configurar preferencias
- **Página**: `/account-settings`
- **Selector**: `input[name="chatbot_enabled"], select[name="language"]`
- **Acción**: Establece tus preferencias
- **Ayuda**: Habilita o deshabilita el asistente de chatbot de IA, y establece tu idioma preferido para la interfaz.
- **Texto de acción**: Siguiente

### Paso 4: Guardar cambios
- **Página**: `/account-settings`
- **Selector**: `button[type="submit"]`
- **Acción**: Guarda tu configuración
- **Ayuda**: Haz clic en "Guardar cambios" para aplicar tus actualizaciones. Tu configuración se guardará inmediatamente.
- **Texto de acción**: Entendido

## Requisitos de contraseña

Tu contraseña debe:
- Tener al menos 8 caracteres
- Contener al menos una letra mayúscula
- Contener al menos una letra minúscula
- Contener al menos un número
- No ser una contraseña comúnmente usada

## Consejos

- Cambia tu contraseña regularmente por seguridad
- Habilita notificaciones por correo electrónico para estar actualizado sobre fechas límite
- Establece tu zona horaria correcta para ver horas de fecha límite precisas
- Mantén tu información de contacto actualizada

## Flujos de trabajo relacionados

- [Ver asignaciones](../focal-point/view-assignments.md) - Verifica tus tareas pendientes
