# Estados de envío y qué puedes hacer (guía de permisos)

Usa esta guía para entender por qué falta un botón o está deshabilitado (por ejemplo **Editar**, **Enviar**, **Aprobar** o **Reabrir**).

## Dos cosas controlan lo que puedes hacer

1. **Tu(s) rol(es)** (permisos)
2. **El estado actual** de la asignación/envío

Si cualquiera de los dos no permite una acción, no la verás (o estará deshabilitada).

## Roles comunes (lenguaje simple)

- **Punto focal (entrada de datos)**: puede ingresar datos y enviar (típicamente `assignment_editor_submitter`)
- **Aprobador**: puede aprobar y reabrir (típicamente `assignment_approver`)
- **Administrador**: puede gestionar usuarios/plantillas/asignaciones (varía según los roles de administrador)

## Estados comunes (qué significan generalmente)

Los nombres de estado pueden variar ligeramente según el flujo de trabajo, pero generalmente se mapean a:

- **No iniciado**: aún no hay respuestas guardadas (o el usuario no lo ha abierto)
- **En progreso / Borrador**: algunas respuestas están guardadas, no enviadas
- **Enviado**: enviado para revisión (la edición puede estar bloqueada)
- **Aprobado**: aceptado/finalizado (la edición generalmente está bloqueada)
- **Reabierto / Devuelto**: enviado de vuelta para corrección (la edición se permite nuevamente)
- **Cerrado / Archivado** (si se usa): período de recopilación terminado; los cambios pueden estar bloqueados

## Qué puedes hacer (matriz rápida)

Esta tabla muestra el comportamiento *típico*.

| Estado | Punto focal (entrada de datos) | Aprobador | Administrador (gestión de asignaciones) |
|---|---|---|---|
| No iniciado | Editar | Ver | Ver / Gestionar |
| En progreso / Borrador | Editar / Enviar | Ver | Ver / Gestionar |
| Enviado | Ver (edición generalmente bloqueada) | Aprobar / Reabrir | Ver / Gestionar |
| Aprobado | Ver | Ver (puede seguir reabriendo) | Ver / Gestionar |
| Reabierto / Devuelto | Editar / Re-enviar | Ver / Aprobar | Ver / Gestionar |

Notas:
- Si no puedes **ver** una asignación en absoluto, generalmente es un problema de **acceso al país** o **rol**.
- Algunas configuraciones permiten que administradores/aprobadores editen después del envío; otras no.

## Cuando faltan botones (causas comunes)

### Falta "Enviar" o está deshabilitado

Causas probables:
- Falta un campo requerido
- Existen mensajes de validación
- La asignación ya está enviada/aprobada y está bloqueada

Qué hacer:
- Corrige los mensajes requeridos/de validación e intenta de nuevo
- Si está bloqueada, pide a un aprobador/administrador que la **Reabra** (si tu flujo de trabajo lo admite)

### Falta "Aprobar"

Causas probables:
- No tienes el rol de aprobador (`assignment_approver`)
- El envío aún no está en un estado "Enviado"

### Falta "Reabrir"

Causas probables:
- El flujo de trabajo no permite reabrir, o solo ciertos roles pueden reabrir
- El envío ya está en progreso (no enviado)

### Falta "Editar"

Causas probables:
- Solo tienes un rol de visualizador
- El estado es enviado/aprobado y la edición está bloqueada

## Si aún estás atascado

- [Solución de problemas (Punto focal)](../focal-point/troubleshooting.md)
- [Obtener ayuda](getting-help.md)
- Pregunta a tu administrador si el problema tiene que ver con acceso, roles o la configuración del flujo de trabajo.
