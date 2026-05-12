# Ejecutar un ciclo de reportes (guía de administrador)

Usa esta guía cuando necesites ejecutar una ronda de recopilación de extremo a extremo (desde preparar una plantilla hasta exportar datos aprobados).

## Antes de comenzar

- Necesitas acceso de **Administrador** para plantillas y asignaciones.
- Acuerda internamente:
  - el nombre del período de reportes (ejemplo: "2026 T1")
  - la lista de países participantes
  - qué significa "buena calidad" (documentos requeridos, expectativas de validación)

## Paso 1 — Preparar la plantilla

1. Abre **Panel de administración** → **Gestión de formularios y datos** → **Gestionar plantillas**.
2. Abre la plantilla que usarás.
3. Confirma que la plantilla es:
   - clara (etiquetas/texto de ayuda)
   - no demasiado estricta (campos requeridos razonables)
   - consistente (opciones de lista desplegable estandarizadas)
4. Si hiciste ediciones, prueba con una pequeña asignación borrador.

Consejo: Para cambios complejos, sigue [Generador de formularios (avanzado)](form-builder-advanced.md).

## Paso 2 — Crear la asignación

1. Abre **Panel de administración** → **Gestión de formularios y datos** → **Gestionar asignaciones**.
2. Haz clic en **Crear** (o similar).
3. Selecciona:
   - la plantilla
   - los países (u organizaciones) incluidos
   - la fecha de inicio y la fecha límite
4. Agrega un mensaje de instrucción corto:
   - qué necesitas
   - la fecha límite
   - a quién contactar para preguntas

## Paso 3 — Confirmar acceso (antes del lanzamiento)

Para cada país:
- Confirma que los puntos focales tienen:
  - el rol de asignación correcto (entrada de datos)
  - el acceso al país correcto

Si esperas documentos de respaldo:
- Confirma que los usuarios correctos tienen un rol que permite cargas (ver [Documentos de respaldo (administrador)](supporting-documents.md)).

## Paso 4 — Monitorear el progreso durante la recopilación

Durante el período abierto, monitorea:
- no iniciado
- en progreso
- enviado
- vencido

Qué hacer cuando el progreso es bajo:
- envía recordatorios (cortos + específicos)
- aclara campos confusos (etiquetas/texto de ayuda)
- extiende la fecha límite si tu flujo de trabajo lo permite

## Paso 5 — Revisar y aprobar envíos

1. Abre la asignación.
2. Revisa los envíos para:
   - valores faltantes que deberían existir
   - valores atípicos (valores muy fuera del rango esperado)
   - documentos requeridos (si aplica)
3. Aprueba envíos que cumplan el estándar mínimo de calidad.
4. Reabre/devuelve envíos que necesiten corrección (con una explicación corta de qué corregir).

Consejo: Usa [Estados de envío y qué puedes hacer](../common/submission-statuses-and-permissions.md) para explicar por qué "Editar/Enviar" está bloqueado/desbloqueado.

## Paso 6 — Exportar datos para reportes

1. Navega a la página del formulario de entrada para cada asignación/país que quieras exportar:
   - Abre la asignación desde **Gestionar asignaciones**.
   - Haz clic en un país/entidad para abrir el formulario de entrada.
2. Usa las opciones de exportación disponibles en la página del formulario de entrada:
   - **Exportar plantilla Excel** (si está habilitado): Descarga un archivo Excel con estructura de formulario y datos.
   - **Exportar PDF** (si está habilitado): Descarga una versión PDF del formulario con datos actuales.
3. Guarda archivos exportados con una convención de nomenclatura consistente:
   - `2026-Q1_TemplateName_CountryName.xlsx` (para exportaciones de países individuales)
   - Nota: Las exportaciones son por país/entidad, no para todos los países a la vez desde la lista de asignaciones.
4. Si necesitas análisis repetible, mantén ID/códigos en la exportación (no los elimines).

Para orientación de interpretación, ver [Exportaciones: cómo interpretar archivos](exports-how-to-interpret.md).

## Paso 7 — Cerrar y documentar decisiones

Al final del ciclo:
- Registra cualquier cambio a mitad del ciclo (extensiones de fecha límite, actualizaciones de plantilla).
- Registra tu regla para duplicados (especialmente para envíos públicos).
- Captura problemas conocidos para mejorar el próximo ciclo.

## Problemas comunes

- **Un país no puede ver la asignación**: faltan roles y acceso al país.
- **Los usuarios no pueden enviar**: demasiados campos requeridos o validación estricta; agrega texto de ayuda y reduce los requeridos.
- **Los cambios en la plantilla causaron confusión**: evita grandes ediciones a mitad del ciclo; despliega mediante una nueva asignación.
- **La exportación no coincide con las expectativas**: confirma que exportaste la asignación correcta y la versión de plantilla.

## Relacionado

- [Ciclo de vida de una asignación](assignment-lifecycle.md)
- [Gestionar asignaciones](manage-assignments.md)
- [Revisar y aprobar envíos](review-approve-submissions.md)
- [Exportar y descargar datos](export-download-data.md)
