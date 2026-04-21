# Solución de problemas de acceso (Administrador)

Usa esta página cuando un usuario reporta que no puede iniciar sesión o no puede ver las páginas/datos que necesita.

## Un usuario no puede iniciar sesión

Lista de verificación:

- Confirma que la dirección de correo electrónico es correcta.
- Confirma que la cuenta está **activa** (no desactivada).
- Si tu flujo de trabajo usa restablecimientos de contraseña, establece una nueva contraseña y compártela **de forma segura**.

## Un punto focal puede iniciar sesión, pero no puede ver asignaciones

Causa más común: **no está asignado a un país/organización** o faltan roles de asignación.

Qué verificar:

1. Abre **Panel de administración → Gestión de usuarios → Gestionar usuarios**.
2. Abre el usuario.
3. Ve a la pestaña **Detalles del usuario** y confirma:
   - Tienen un **rol de asignación** (por ejemplo, `assignment_editor_submitter` o `assignment_viewer`)
4. Ve a la pestaña **Permisos de entidad** y confirma:
   - Al menos un **país** (u organización) está asignado
5. Confirma que hay una asignación creada para ese país/organización.

## Un usuario dice "Acceso denegado" para una página de administración

Esto generalmente significa que faltan los permisos requeridos.

Qué hacer:

- Confirma si el usuario debe tener **roles de administrador** o **roles de asignación** (o ambos).
- Si deben ser administrador, asigna los roles de administrador apropiados (por ejemplo `admin_full`, `admin_core`, o roles de gestión específicos).
- Solo los Gestores del sistema pueden asignar roles - contacta a un Gestor del sistema para actualizar los roles del usuario.

## Un usuario no puede ver un país específico

Causas comunes:

- El usuario no está asignado a ese país.
- El rol del usuario no permite acceso a esa área.

Qué hacer:

1. Ve a la pestaña **Permisos de entidad** del usuario y confirma que están asignados al país/países correctos (u organizaciones).
2. Si esto es un flujo de trabajo de administración, confirma que tienen el/los rol(es) de administrador relevantes (por ejemplo `admin_countries_manager` para gestión de países).

## Relacionado

- [Roles y permisos de usuario](user-roles.md) - Entender diferentes roles y permisos
- [Gestionar usuarios](manage-users.md)
- [Agregar un usuario](add-user.md)
- [Obtener ayuda](../common/getting-help.md)
