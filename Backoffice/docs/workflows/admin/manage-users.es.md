---
id: manage-users
title: Gestionar usuarios existentes
description: Guía para editar, desactivar y gestionar cuentas de usuario
roles: [admin]
category: user-management
keywords: [editar usuario, actualizar usuario, desactivar, restablecer contraseña, cambiar rol, modificar cuenta]
pages:
  - /admin/users
  - /admin/users/edit
---

# Gestionar usuarios existentes

Este flujo de trabajo guía a los administradores a través de la gestión de cuentas de usuario existentes, incluyendo edición, desactivación y restablecimiento de contraseñas.

## Prerrequisitos

- Se requiere rol de administrador
- Acceso a la sección Gestión de usuarios y acceso

## Pasos

### Paso 1: Navegar a la gestión de usuarios
- **Página**: `/admin/users`
- **Selector**: `.user-list, [data-testid="user-list"], table`
- **Acción**: Ver la lista de todos los usuarios
- **Ayuda**: La página Gestión de usuarios muestra todos los usuarios en el sistema. Puedes buscar, filtrar y ordenar usuarios desde aquí.
- **Texto de acción**: Siguiente

### Paso 2: Encontrar el usuario a gestionar
- **Página**: `/admin/users`
- **Selector**: `input[type="search"], .search-input, [data-testid="search"]`
- **Acción**: Busca el usuario
- **Ayuda**: Usa el cuadro de búsqueda para encontrar un usuario específico por nombre o correo electrónico. También puedes usar filtros para reducir la lista.
- **Texto de acción**: Siguiente

### Paso 3: Abrir formulario de edición de usuario
- **Página**: `/admin/users`
- **Selector**: `a[href*="/admin/users/edit"], .edit-user-btn, [data-action="edit"]`
- **Acción**: Haz clic en el icono de edición junto al usuario
- **Ayuda**: Haz clic en el icono de edición (lápiz) junto al usuario que quieres modificar. Esto abre el formulario de edición de usuario.
- **Texto de acción**: Continuar

### Paso 4: Modificar detalles del usuario
- **Página**: `/admin/users/edit`
- **Selector**: `#user-details-panel, form`
- **Acción**: Actualiza la información del usuario según sea necesario
- **Ayuda**: Puedes actualizar el nombre, correo electrónico, rol y contraseña del usuario. Los cambios tienen efecto inmediatamente después de guardar.
- **Campos**:
  - Nombre completo: Actualiza el nombre del usuario
  - Correo electrónico: Cambia el correo electrónico de inicio de sesión (el usuario necesitará verificar)
  - Rol: Cambia entre Administrador y Punto focal
  - Contraseña: Deja en blanco para mantener la actual, o ingresa una nueva contraseña

### Paso 5: Actualizar permisos
- **Página**: `/admin/users/edit`
- **Selector**: `#entity-permissions-tab`
- **Acción**: Modifica las asignaciones de países
- **Ayuda**: Agrega o elimina países para Puntos focales. Los Administradores automáticamente tienen acceso a todos los países.
- **Texto de acción**: Siguiente

### Paso 6: Guardar cambios
- **Página**: `/admin/users/edit`
- **Selector**: `form button[type="submit"], .fixed button[type="submit"]`
- **Acción**: Haz clic en Guardar cambios
- **Ayuda**: Haz clic en "Guardar cambios" para aplicar tus actualizaciones. El usuario será notificado si su acceso ha cambiado.
- **Texto de acción**: Entendido

## Acciones adicionales

### Desactivar un usuario
Para desactivar una cuenta de usuario:
1. Encuentra el usuario en la lista
2. Haz clic en el interruptor de estado o botón de desactivar
3. Confirma la desactivación

Los usuarios desactivados no pueden iniciar sesión pero sus datos se conservan.

### Restablecer contraseña
Para restablecer la contraseña de un usuario:
1. Abre el formulario de edición de usuario
2. Ingresa una nueva contraseña en el campo de contraseña
3. Guarda los cambios
4. Comparte la nueva contraseña con el usuario de forma segura

## Consejos

- Desactivar un usuario preserva todos sus datos y envíos
- Los cambios de rol tienen efecto en el próximo inicio de sesión del usuario
- Considera usar el panel de Analíticas para revisar la actividad del usuario antes de hacer cambios
- Los registros de auditoría rastrean todas las acciones de gestión de usuarios

## Flujos de trabajo relacionados

- [Agregar nuevo usuario](add-user.md) - Crear nuevas cuentas de usuario
