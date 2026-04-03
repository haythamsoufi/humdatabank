# Recetas de roles (tareas administrativas comunes)

Usa esta página cuando no estés seguro de qué roles asignar para una tarea específica.

## Antes de comenzar

- Los roles controlan **qué páginas/acciones** un usuario puede acceder.
- Muchos usuarios también necesitan **acceso al país** para ver asignaciones para países específicos.

## Receta: Punto focal estándar (entrada de datos)

Dale al usuario:

- Rol: `assignment_editor_submitter`
- Acceso al país: asigna al menos un país

Pueden:
- ver asignaciones para sus países
- ingresar datos y enviar

## Receta: Punto focal que también aprueba

Dale al usuario:

- Roles: `assignment_editor_submitter`, `assignment_approver`
- Acceso al país: asigna los países relevantes

## Receta: Visualizador de solo lectura

Dale al usuario:

- Rol: `assignment_viewer`
- Acceso al país: opcional (depende de cómo esté configurado tu sistema)

## Receta: Diseñador de plantillas (sin gestión de usuarios)

Dale al usuario:

- Un rol de gestión de plantillas (por ejemplo: `admin_templates_manager`)

Opcionalmente también:

- `assignment_viewer` (para que puedan ver cómo se usan las plantillas)

## Receta: Gestor de asignaciones (sin ediciones de plantilla)

Dale al usuario:

- `admin_assignments_manager`

Opcionalmente:

- `assignment_viewer` o `assignment_approver` si también revisan envíos

## Receta: Gestor de usuarios (RH / administrador de acceso)

Dale al usuario:

- `admin_users_manager`

Pueden crear/gestionar usuarios y asignar roles (dentro de su alcance permitido).

## Receta: Cargador de documentos solamente

Dale al usuario:

- `assignment_documents_uploader`
- Acceso al país (si lo requiere tu configuración)

Pueden cargar documentos de respaldo pero no enviar datos de formulario.

## Problemas comunes

- **El usuario no puede ver asignaciones**: generalmente necesitan tanto (1) un rol de asignación como (2) acceso al país.
- **El usuario ve "Acceso denegado"**: les falta el rol específico para ese módulo de administración.

## Relacionado

- [Roles y permisos de usuario](user-roles.md)
- [Gestionar usuarios](manage-users.md)
- [Solución de problemas de acceso (Administrador)](troubleshooting-access.md)
