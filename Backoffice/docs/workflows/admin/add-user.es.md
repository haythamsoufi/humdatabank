---
id: add-user
title: Agregar Nuevo Usuario
description: Guía para crear una nueva cuenta de usuario en el sistema
roles: [admin]
category: user-management
keywords: [crear usuario, nueva cuenta, registrar, personal, miembro, registro]
pages:
  - /admin/users
  - /admin/users/new
---

# Agregar Nuevo Usuario

Este flujo de trabajo guía a los administradores a través de la creación de una nueva cuenta de usuario en el sistema.

## Requisitos Previos

- Se requiere rol de administrador
- Acceso a la sección de Gestión de Usuarios y Accesos

## Pasos

### Step 1: Navegar a Gestión de Usuarios
- **Page**: `/admin/users`
- **Selector**: `a[href="/admin/users/new"]`
- **Action**: Haga clic en el botón "Agregar Nuevo Usuario"
- **Help**: Haga clic en el botón "Agregar Nuevo Usuario" en la esquina superior derecha para comenzar a crear una nueva cuenta de usuario.
- **ActionText**: Continuar

### Step 2: Completar Detalles del Usuario
- **Page**: `/admin/users/new`
- **Selector**: `#user-details-panel`
- **Action**: Complete la información requerida del usuario
- **Help**: Ingrese el correo electrónico, nombre, rol del usuario y establezca una contraseña inicial. Todos los campos marcados con * son obligatorios.
- **ActionText**: Siguiente

### Step 3: Configurar Permisos de Entidad
- **Page**: `/admin/users/new`
- **Selector**: `#entity-permissions-tab, #entity-permissions-panel`
- **Action**: Haga clic en la pestaña Permisos de Entidad
- **Help**: Asigne países o entidades organizacionales al usuario. Los Puntos Focales deben tener al menos un país asignado para acceder a los datos.
- **ActionText**: Siguiente

### Step 4: Guardar el Nuevo Usuario
- **Page**: `/admin/users/new`
- **Selector**: `form button[type="submit"], .fixed button[type="submit"]`
- **Action**: Haga clic en Crear Usuario
- **Help**: Revise toda la información y haga clic en "Crear Usuario" para completar. El usuario recibirá sus credenciales de acceso.
- **ActionText**: Entendido

## Consejos

- Los usuarios deberán cambiar su contraseña en el primer inicio de sesión por seguridad
- Los Puntos Focales están limitados a los datos de sus países asignados únicamente
- Los administradores tienen acceso completo al sistema en todos los países
- Siempre puede editar los detalles del usuario más tarde desde la página de Gestión de Usuarios

## Flujos de Trabajo Relacionados

- [Gestionar Usuarios](manage-users.md) - Editar y desactivar usuarios existentes
