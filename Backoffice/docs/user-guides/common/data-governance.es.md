# Gobernanza de Datos: Cómo la Soporta el Sistema

Este documento describe cómo el Banco de Datos Humanitarios apoya la **gobernanza de datos**: las políticas y controles que garantizan que los datos recogidos sean accesibles solo para las partes autorizadas, sean coherentes y fiables, rastreables y gestionados de forma segura. Está destinado a administradores, puntos de interés y otros que necesitan entender cómo la plataforma apoya la gobernanza sobre los datos que recopila.

## Alcance de este documento

- **Propiedad de datos** — Propietarios de plantillas y propietarios de datos con responsabilidad explícita por asignación
- **Control de acceso y alcance de datos** — Quién puede ver y modificar qué datos, con detección de acceso fantasma
- **Calidad y consistencia de datos** — Validación, definiciones estándar, seguimiento de los retrasos y el flujo de trabajo de envío
- **Rendición de cuentas y auditoría** — Atribución de acciones administrativas, seguimiento de presentación/aprobación y auditoría de activación
- **Cumplimiento** — Seguimiento del cumplimiento de documentos FDRS
- **Metadatos** — Definiciones de indicadores, etiquetas de formularios y detección de sugerencias obsoletas
- **Ciclo de vida de los datos** — Desde el borrador hasta la aprobación, y cómo se controlan los cambios
- **Manejo seguro** — Exportaciones, enlaces públicos y prácticas de privacidad
- **Prácticas operativas** — Ejecutar ciclos de informes y mantener la gobernanza en el uso diario
- **Panel de Gobernanza** — Una página de administración dedicada que muestra métricas, indicadores y una puntuación de salud en todos los pilares

---

## Propiedad de los datos

La plataforma implementa un **modelo de propiedad de datos de dos niveles** que distingue la responsabilidad en diferentes niveles.

### Nivel 1: Propietario de la plantilla (nivel plantilla)

Un **Propietario de la Plantilla** es responsable del *estándar o definición* de los datos — qué se mide y cómo.

- **Propietario de la Plantilla** (`FormTemplate.owned_by`) — Cada plantilla de formulario puede tener un propietario: la persona responsable del estándar de datos que define. Solo los usuarios con permisos de plantilla a nivel de administrador aparecen en el desplegable del Propietario de la Plantilla. Configura esto en **Panel de administración → Constructor de formularios → Plantilla de edición**.

### Nivel 2: Propietario de los datos (nivel de asignación)

Un **Propietario de Datos** es responsable de los *datos reales recogidos* en un ciclo de informes específico.

- **Propietario de los Datos de la Asignación** (`AssignedForm.data_owner_id`) — Cada asignación puede tener un propietario de datos designado: la persona responsable de la calidad de los datos durante ese ciclo de recogida. Solo los usuarios con permisos de asignación a nivel de administrador aparecen en el desplegable de Propietarios de Datos (los puntos focales se excluyen porque son remitentes, no propietarios). Configúralo bajo **Panel de Administración → Asignaciones → Crear/Editar Asignación**.
- Cuando se crea una nueva asignación y se selecciona una plantilla, el sistema puede precompletar el propietario de datos desde el propietario de la plantilla (`owned_by`).

### Nivel 3: Punto Focal (nivel nacional)

**Los puntos focales** son la responsabilidad existente a nivel de entidad. Se asigna un punto focal a uno o más países y es responsable de introducir y enviar los datos de esos países. Los puntos focales no son propietarios de los datos; son los usuarios operativos que recopilan y envuen.

### Datos de organizaciones (países, sociedades nacionales, estructura de sociedades nacionales)

Los datos de la organización son la **referencia autorizada** para el alcance geográfico y estructural a lo largo de la plataforma: países, Sociedades Nacionales y — cuando la característica está habilitada — estructura de las Sociedades Nacionales (sucursales, sub-sucursales, unidades locales).

- **Países** — La lista de países se mantiene bajo **Panel de Administración → Gestión de Organizaciones** (pestaña Países). Solo los usuarios con los permisos requeridos pueden crear, editar o eliminar países. Esta lista sustenta el alcance de la asignación (qué países están incluidos en una asignación), el acceso por país del usuario (a qué países puede acceder un punto focal) y la información (por ejemplo, exportaciones por país).
- **Sociedades Nacionales** — Cada Sociedad Nacional está asociada con un país. Las Sociedades Nacionales se gestionan bajo **Gestión Organizacional → Sociedades Nacionales**, y se utilizan cuando los informes o asignaciones están sujetos a la Sociedad Nacional en lugar de, o además de, país.
- **Estructura de la Sociedad Nacional (sucursales, subramas, unidades locales)** — Cuando la característica de estructura de la Sociedad Nacional está activada, la jerarquía es **País → rama → Subrama → unidad local**. Las sucursales y subramas están asociadas a un país; Las unidades locales pertenecen a una rama o sub-rama. Esta estructura se mantiene bajo **Gestión Organizacional → estructura de Sociedad Nacional** y proporciona la lista canónica de ramas y unidades locales utilizadas en formularios, asignaciones e informes.

**Propietario y mantenimiento de datos.** El **propietario de datos** para todos los datos de la organización es el **equipo de Sistemas de Datos (FDS) a nivel de Federación**. FDS es responsable de la exactitud y la gobernanza de estas listas maestras. Solo los usuarios con los permisos requeridos pueden modificar los datos en el sistema: **Editar países** (`admin.countries.edit`) para países, y **Gestionar organización** (`admin.organization.manage`) para la estructura completa. El acceso de solo lectura utiliza **Ver países** (`admin.countries.view`). Los administradores designados (bajo la gobernanza FDS) mantienen los datos para que los datos de formularios, asignaciones y exportaciones permanezcan alineados con una única jerarquía.

Mantener los datos de la organización precisos garantiza una atribución correcta, un control de acceso que se ajuste a la estructura prevista y exportaciones e informes que respeten los límites de la organización.

*Ver:* [Roles y permisos de usuario](../admin/user-roles.md) (para roles que incluyen la gestión de países y organizaciones)

### Banco de Indicadores (glosario de definiciones estándar)

El **Banco de Indicadores** es un **glosario empresarial** centralizado de definiciones de indicadores (nombre, unidad, definición y, opcionalmente, reglas de cálculo). No almacena los valores enviados — estos son datos en formato y están vinculados a asignaciones y entidades (por ejemplo, país o Sociedad Nacional).

Solo los usuarios con permisos del Banco Indicador (por ejemplo, **Gestor del Banco Indicador**) pueden ver, crear, editar, archivar o revisar sugerencias de indicadores. El Banco de Indicadores define *qué* se mide; Registros de datos del formulario *quién* informó *cuál* valor y *cuándo*. Mantener las definiciones estables a lo largo del tiempo; Cuando cambia el significado de una medida, añade un nuevo indicador para que los datos históricos sigan siendo interpretables.

La gestión central de las definiciones evita interpretaciones contradictorias entre países y períodos y apoya informes comparables.

*Ver:* [Banco de Indicadores (admin)](../admin/indicator-bank.md)

### Resumen

| Tipo de datos | Propietario | Donde se mantenía | Papel en la gobernanza |
|-----------|-------|------------------|---------------------|
| Países, Sociedades Nacionales, Estructura de la Sociedad Nacional | **FDS** (Equipo de Sistemas de Datos a nivel de Federación) | Panel de Administración → Gestión de Organizaciones | Alcance autoritativo para asignaciones, acceso de usuarios e informes |
| Definiciones de indicadores (términos del glosario) | **Gerentes del Banco Indicador** | Panel de administración → Banco de Indicadores | Definiciones estándar utilizadas entre plantillas y asignaciones |
| Normas para plantillas de formulario | **Propietario de la plantilla** (usuario único por plantilla) | Panel de administración → Constructor de formularios | Define qué datos se recopilan y cómo |
| Datos de asignación (ciclo de recogida) | **Propietario de datos** (usuario único por asignación) | Panel de Administración → Asignaciones | Responsable de la calidad de los datos durante el ciclo de informes |
| Valores de envío de formularios | **Punto Focal** (por país/entidad) | Formularios de inscripción, envíos, exportaciones | Datos atribuidos a la entidad que lo presenta |

### Filtrado desplegable para roles de propiedad

Para mantener una clara separación de preocupaciones, la plataforma filtra los desplegables de usuario según el rol:

| Desplegable | Programas | Excluye | Razón |
|----------|-------|----------|--------|
| Propietario de la plantilla | Usuarios con permisos de plantilla de administrador | Puntos focales, usuarios solo de vista | Solo los administradores deberían poseer los estándares de datos |
| Propietario de Datos de Asignación | Usuarios con permisos de asignación de administrador | Puntos focales, usuarios solo de vista | Los puntos focales presentan datos; Los propietarios son responsables de ello |
| Acceso Compartido (plantilla) | Usuarios con roles de administrador | Usuarios no administrativos | El intercambio de plantillas es una preocupación a nivel administrativo |

---

## 1. Control de acceso y alcance de datos

El sistema restringe el acceso para que los usuarios puedan ver y actuar únicamente sobre los datos a los que están autorizados a acceder.

### Control de acceso basado en roles (RBAC)

- A los usuarios se les asignan **roles** que definen acciones permitidas (ver, editar, enviar, aprobar, gestionar plantillas, etc.).
- **Los roles de asignación** (por ejemplo, visor, editor/remitente, aprobador) determinan si un usuario solo puede ver datos, introducirlos y enviarlos, o aprobarlos.
- **Los roles administrativos** regulan el acceso a plantillas, asignaciones, usuarios, países, indicadores, contenido, análisis y funciones de seguridad/auditoría.
- Las acciones no permitidas por el rol del usuario no están disponibles; Los botones y páginas relevantes están ocultos o deshabilitados.

*Ver:* [Roles y permisos de usuario](../admin/user-roles.md)

### País y alcance de asignación

- **Asignación de país (o entidad)** determina *qués* asignaciones y datos de envío puede ver un usuario.
- Un punto focal normalmente solo tiene acceso a las asignaciones de los países a los que está asignado.
- Los administradores con acceso a la gestión de asignaciones ven las asignaciones según sus permisos; El alcance puede verse aún más limitado por la configuración.
- Si un usuario no puede acceder a una asignación, la causa suele ser **acceso por país** o **rol**, en lugar de los datos en sí.

*Ver:* [Estado de envío y qué puedes hacer](submission-statuses-and-permissions.md), [Resolución de problemas de acceso (Admin)](../admin/troubleshooting-access.md)

### Detección de acceso fantasma

El **Panel de Gobernanza** detecta **acceso fantasma**: usuarios inactivos (desactivados) que aún mantienen roles RBAC. Esto supone un riesgo de seguridad porque las concesiones de rol pueden persistir después de que un usuario abandone la organización. El panel señala a estos usuarios y enlaza directamente con la gestión de usuarios para su remediación.

Además, el salpicadero marca:
- **Usuarios con permisos de entidad (país) pero sin rol RBAC** — pueden iniciar sesión pero no pueden hacer nada útil
- **Permisos huérfanos** — permisos no asignados a ningún rol o concesión
- **Roles con cero usuarios** — roles que existen pero no tienen miembros

### Resumen

| Preocupación | Cómo lo soporta el sistema |
|---------|----------------------------|
| ¿Quién puede ver los datos | Roles y asignación de país/entidad; los usuarios ven solo los datos a los que están autorizados a acceder |
| Quién puede modificar los datos | Usuarios con roles de edición/envío o administradores; los aprobadores pueden reabrir para correcciones |
| ¿Quién puede exportar | Usuarios con acceso al formulario de asignación y inscripción; La exportación puede estar habilitada por plantilla |
| Acceso fantasma | El Panel de Gobernanza marca usuarios inactivos con roles activos en RBAC |
| Roles no utilizados | El Panel de Gobernanza marca roles con cero usuarios asignados |

---

## 2. Calidad y consistencia de los datos

El sistema soporta datos consistentes y adecuados a su propósito mediante definiciones estándar (Banco de Indicadores), campos de validación y requisitos, y un flujo de trabajo claro de envío y aprobación.

### Banco de indicadores (definiciones estándar)

Vincular los campos de formulario a indicadores en el Banco de Indicadores garantiza que la misma medida se informe de la misma manera entre países, periodos y plantillas. Consulta [Propiedad de los datos](#data-ownership) para saber quién los mantiene.

*Ver:* [Banco de Indicadores (admin)](../admin/indicator-bank.md)

### Validación y campos requeridos

**Los campos requeridos** y **reglas de validación** (por ejemplo, formato numérico, rangos) impiden la presentación hasta que el formulario cumple con la calidad mínima. Los mensajes de validación aparecen en el formulario y bloquean la envío hasta que se resuelvan. Los administradores definen estos en el Constructor de Formularios.

*Ver:* [Constructor de formularios (avanzado)](../admin/form-builder-advanced.md), [Editar una plantilla](../admin/edit-template.md)

### Flujo de trabajo de envío y aprobación

Los datos pasan por **estados** (por ejemplo, no iniciados → en progreso → enviados → aprobados). **Enviar** enviada para revisión; **Aproba** lo acepta; **Reabrir** lo devuelve para corregirlo. Cuando se utiliza un bloqueo de edición, los datos se consideran definitivos solo tras la aprobación.

El sistema registra a **quién ha presentado** (`submitted_by_user_id`) y **quién ha aprobado** (`approved_by_user_id`) cada cambio de estado de entidad, proporcionando un claro seguimiento de auditoría de responsabilidad.

*Ver:* [Estado de las propuestas y lo que puedes hacer](submission-statuses-and-permissions.md), [Revisar y aprobar las propuestas](../admin/review-approve-submissions.md)

### Seguimiento atrasado y gravedad

El **Panel de Gobernanza** rastrea las entregas atrasadas con categorías de gravedad:

| Gravedad | Umbral | Significado |
|----------|-----------|---------|
| **Crítico** | > 30 días de retraso | Requiere atención inmediata |
| **Alto** | > 8 días de retraso | Necesita seguimiento |
| **Medio** | > 1 día de retraso | Recientemente atrasado |

El panel también detecta **asignaciones nunca iniciadas** (asignaciones activas donde cada entidad sigue en estado "Pendiente") y **asignaciones sin entidad** (creadas pero nunca asignadas a ningún país).

### Resumen

| Preocupación | Cómo lo soporta el sistema |
|---------|----------------------------|
| Definiciones consistentes | Banco de Indicadores; Campos de formulario vinculados a indicadores |
| Completitud mínima | Los campos obligatorios y las reglas de validación bloquean la presentación hasta que se cumpla |
| Limpiar estado final | Flujo de trabajo de envío y aprobación; estados y, cuando se utilicen, editar el bloqueo tras enviar |
| Seguimiento atrasado | Panel de Gobernanza con categorías de severidad (crítica/alta/media) |
| Detección nunca iniciada | El panel de control marca asignaciones activas donde ningún país ha comenzado a trabajar |
| Atribución | `submitted_by` y `approved_by` rastreados por cambio de estado de entidad |

---

## 3. Rendición de cuentas y auditoría

### Registro de acciones administrativas y niveles de riesgo

El sistema registra las acciones administrativas (quién hizo qué, cuándo) y asigna a cada una un **nivel de riesgo** (alto, medio, bajo). **Las acciones de alto riesgo** (por ejemplo, eliminación de usuarios, cambios en el rol del gestor del sistema) crean automáticamente **eventos de seguridad** y se resaltan para su revisión. Todas las acciones forman parte de la **pista de auditoría** para el cumplimiento y la resolución de problemas.

*Ver:* [Niveles de riesgo de acción administrativa](../../workflows/admin/admin-action-risk-levels.md)

Las acciones de alto y crítico riesgo aparecen en el **Panel de Seguridad** y en los registros de acciones administrativas; Las acciones pueden filtrarse por nivel de riesgo.

### Auditoría del ciclo de vida de la asignación

El sistema rastrea quién activó y desactivó las asignaciones:

- `activated_by_user_id` — registrado cuando una asignación se activa o se reabre
- `deactivated_by_user_id` — registrado cuando una asignación se desactiva o cierra

Esto garantiza que cada cambio en el ciclo de vida se atribuya a un usuario específico.

### Responsabilidad de la presentación

Para cada estado de país/entidad dentro de una asignación:

- `submitted_by_user_id` — registrado cuando un punto focal envia datos
- `approved_by_user_id` — registrado cuando un administrador aprueba la presentación

Estos campos se activan automáticamente en el momento de la acción y no pueden editarse, proporcionando atribución resistente a manipulaciones.

### Resumen

| Preocupación | Cómo lo soporta el sistema |
|---------|----------------------------|
| Atribución de cambios | Acciones de administrador registradas con usuario, tipo de acción, descripción y destino |
| Revisión de acciones sensibles | Niveles de riesgo; las acciones de alto riesgo generan eventos de seguridad y aparecen en el Panel de Seguridad |
| Ciclo de vida de la asignación | `activated_by` y `deactivated_by` rastreados para cada asignación |
| Atribución de envío | `submitted_by` y `approved_by` rastreados por cambio de estado de entidad |
| Cumplimiento | Seguimiento completo de auditoría de las acciones administrativas para revisión e informes |

---

## 4. Cumplimiento (Documentos FDRS)

El Panel de Gobernanza rastrea **el cumplimiento de documentos FDRS**: si los países han presentado los documentos requeridos (Informe Anual y Estado Financiero Auditado) en los periodos de informe recientes.

- **Tasa de cumplimiento** — porcentaje de países que han presentado los documentos requeridos
- **Países no conformes** — marcados con una lista que puede ampliarse para ver países individuales
- **Umbral de cumplimiento** — el panel considera 70% or superior como "OK" para la puntuación de salud

---

## 5. Completitud de metadatos

Los buenos metadatos apoyan la descubribilidad y la consistencia. El Panel de Gobernanza sigue los siguientes seguimientos

- **Indicadores con definición** — porcentaje de indicadores activos que tienen un campo de definición no vacío
- **Elementos del formulario con etiqueta** — porcentaje de elementos del formulario en todas las plantillas que tienen una etiqueta de visualización
- **Indicadores archivados** — recuento de indicadores movidos a estado de archivo
- **Plantillas publicadas nunca asignadas** — plantillas que se han publicado pero nunca se han utilizado en una tarea (posible desperdicio o descuidad)
- **Sugerencias obsoletas** — sugerencias indicadoras enviadas hace más de 30 días que no han sido revisadas

---

## 6. Ciclo de vida de los datos y control de los cambios

Cuando el camino desde el borrador hasta la aprobación está claro y los cambios están controlados, la gobernanza es más fácil de mantener.

### Estatus y permisos

Cada envío tiene un **estado** (por ejemplo, no iniciado, en progreso, enviado, aprobado, reabierto). Lo que un usuario puede hacer (editar, enviar, aprobar, reabrir) depende del **rol** y del **estado actual**. Esto evita ediciones ad hoc tras la entrega, a menos que el flujo de trabajo permita reabrirlo.

*Ver:* [Estado de las publicaciones y lo que puedes hacer](submission-statuses-and-permissions.md)

### Reapertura y correcciones

**Reabrir** (por aprobadores o administradores) devuelve una publicación para que el punto focal pueda corregir y volver a enviarla. La elección entre reabrir o crear una nueva asignación es una decisión de proceso; Documenta las reaperturas (por ejemplo, en comentarios o procedimientos) para que la pista de auditoría se mantenga limpia.

*Ver:* [Revisar y aprobar propuestas](../admin/review-approve-submissions.md)

### Duplicados y envíos públicos

Para envíos de **URL pública**, el sistema no impide duplicados. Define y documenta cómo se gestionan los duplicados (por ejemplo, conservar el último, conservar el mejor, revisión manual) y qué significa "calidad mínima" (campos requeridos, documentos), y luego aplicar el flujo de validación y aprobación de forma consistente.

*Ver:* [Envíos de URL públicas](../admin/public-url-submissions.md)

### Resumen

| Preocupación | Cómo lo soporta el sistema |
|---------|----------------------------|
| Ciclo de vida limpio | Estatus (borrador → presentado → aprobado) y acciones basadas en roles |
| Cambios controlados tras enviar | Reabrir por aprobador; editar bloqueo donde está configurado |
| Duplicados y calidad para URLs públicas | Lista de verificación de gobernanza y procesos coherentes; Validación y revisión en la plataforma |

---

## 7. Manejo seguro de datos

La gobernanza incluye cómo se exportan, comparten y protegen los datos.

### Exportaciones (Excel, PDF)

Las exportaciones están disponibles para los usuarios con acceso al formulario de asignación y entrada; la plantilla controla si Excel o PDF está habilitado. Trata las exportaciones como algo sensible: no compartas vía enlaces públicos, almacena en ubicaciones aprobadas, conserva una copia sin modificar de las exportaciones en bruto y documenta cualquier limpieza manual.

*Ver:* [Exportar y descargar datos](../admin/export-download-data.md), [Exportaciones: cómo interpretar archivos](../admin/exports-how-to-interpret.md)

### Envíos de URL públicas

Las URLs públicas permiten enviar sin iniciar sesión y pueden compartirse ampliamente, por lo que conllevan un mayor riesgo.
Antes de usar: define quién puede enviar y cómo se comparte la URL, cómo se gestionan los duplicados, qué significa "calidad mínima" y cuándo se desactivará el enlace (por ejemplo, después de la fecha límite). Supervisa las entregas y desactiva el enlace cuando termine el periodo de recolección.

*Ver:* [Envíos de URL públicas](../admin/public-url-submissions.md)

### Manejo de datos y privacidad

Reducir el riesgo evitando identificadores personales innecesarios en envíos y archivos adjuntos, y definiendo quién puede acceder a datos sensibles, cuánto tiempo se conservan y cómo se comparten. La plataforma proporciona control de acceso y auditoría; Tu organización define qué recopilar y cómo almacenar y compartir las exportaciones.

*Ver:* [Manejo de datos y privacidad](data-handling-and-privacy.md)

### Resumen

| Preocupación | Cómo lo soporta el sistema |
|---------|----------------------------|
| ¿Quién puede exportar | Acceso a la asignación y al formulario de inscripción; Exportación habilitada en plantilla |
| Uso seguro de las exportaciones | Documentación y prácticas; la plataforma proporciona control de acceso y auditoría |
| URLs públicas | Lista de verificación de gobernanza, monitorización y desactivación cuando no se usa |
| Privacidad y sensibilidad | Orientación sobre el manejo de datos; Control de acceso y auditoría en la plataforma |

---

## 8. Panel de control de gobernanza

El **Panel de Gobernanza** (Panel de Administración → Gobernanza) es una página administrativa dedicada que muestra métricas, indicadores y enlaces accionables en todos los pilares de gobernanza. Requiere el permiso `admin.governance.view`.

### Puntuación de salud

Una puntuación de salud de gobernanza **0–100** se calcula a partir de puntuaciones ponderadas de pilares:

| Pilar | Peso | Lo que mide |
|--------|--------|------------------|
| Propiedad | 18% | Cobertura de puntos focales, asignación del propietario de datos |
| Control de acceso | 23% | Cobertura RBAC, acceso fantasma, permisos huérfanos |
| Calidad | 23% | Tasa de envíos, seguimiento atrasado |
| Cumplimiento | 23% | Tasa de cumplimiento de documentos FDRS |
| Metadatos | 13% | Definiciones de indicadores, etiquetas de elementos de formulario |

Calificaciones: A (≥ 90), B (≥ 75), C (≥ 60), D (≥ 45), F (< 45).

### Tira KPI

Cinco métricas clave se muestran en la parte superior del panel de control:

1. **Punto Focal %** — porcentaje de países con al menos un punto focal asignado
2. **Activo sin propietario** — número de asignaciones activas sin un propietario de datos designado
3. **Acceso Fantasma** — número de usuarios inactivos que aún ostentan roles RBAC
4. **Tasa de Envío** — porcentaje de los estados de las entidades que se presentan o aprueban
5. **Cumplimiento** — Tasa de cumplimiento de documentos FDRS

### Paneles de sección

Cada pilar de gobernanza tiene un panel detallado con barras de progreso, conteos de banderas y enlaces a las páginas administrativas correspondientes:

- **Propiedad de los datos** — cobertura de puntos focales, cobertura del propietario de datos de asignación (enlaces a Asignaciones con filtro `?no_data_owner=1`)
- **Control de acceso** — Estadísticas RBAC, detección de usuarios fantasma, permisos huérfanos, roles vacíos
- **Estándares de calidad** — tasa de entrega, desglose de gravedad atrasada (crítico/alto/medio), tareas nunca iniciadas, tabla de donuts de distribución de estado
- **Cumplimiento** — Tasa de cumplimiento de documentos FDRS, lista de países no conformes
- **Metadatos** — cobertura de definición de indicadores, cobertura de etiquetas de elementos del formulario, plantillas publicadas nunca asignadas, sugerencias obsoletas

### Políticas y Responsabilidades

Una matriz resumen asigna cada pilar de gobernanza a:
- Lo que cubre
- Quién es responsable
- Cómo gestionarlo
- Estado actual (OK o Huecos)

### Enlaces cruzados con otras páginas administrativas

El Panel de Gobernanza enlaza directamente con las páginas administrativas relevantes con filtros preaplicados:

| Métrica de panel | Enlaces a | Filtro aplicado |
|-----------------|----------|----------------|
| Asignaciones activas sin propietario de datos | Asignaciones | `?no_data_owner=1` (muestra solo asignaciones con el propietario de datos en blanco) |
| Países sin punto focal | Gestión de Asignaciones | Enlace directo |
| Usuarios fantasma | Gestión de usuarios → Editar usuario | Enlace directo por usuario |
| Usuarios con acceso a la entidad pero sin rol | Gestión de usuarios → Editar usuario | Enlace directo por usuario |

---

## 9. Prácticas operativas que apoyan la gobernanza

Las siguientes prácticas ayudan a mantener la gobernanza en el uso diario.

### Ejecutando un ciclo de informes

- **Antes del lanzamiento:** Acordar el periodo de informe, los países participantes y qué significa "buena calidad" (documentos requeridos, expectativas de validación). Asigna un **Propietario de Datos** para la asignación.
- **Acceso:** Confirmar que los puntos focales tienen los roles y el acceso a países correctos antes de que se abra la asignación.
- **Durante la recopilación:** Monitorizar el progreso (no iniciado, en curso, entregado, atrasado) y utilizar validación y recordatorios para mejorar la completitud. Utiliza el Panel de Gobernanza para controlar la gravedad atrasada.
- **Revisión:** Utiliza una lista de verificación consistente (por ejemplo, campos requeridos, valores atípicos, consistencia) al aprobar envíos.
- **Después del ciclo:** Documentar las decisiones (por ejemplo, extensiones de plazos, regla de duplicar para envíos públicos, problemas conocidos) para el siguiente ciclo. Revisa el Panel de Gobernanza para la salud general.

*Ver:* [Ejecutar un ciclo de informes (manual de administración)](../admin/run-a-reporting-cycle.md)

### Plantillas y consistencia

- Utilizar el Banco de Indicadores y vincular los campos del formulario a indicadores cuando se requieran datos comparables entre países y periodos.
- Asignar un **Propietario de la Plantilla** a cada plantilla publicada para que haya un propietario claro para el estándar de datos.
- Evitar cambios sustanciales en la plantilla a mitad de ciclo; Utiliza una nueva asignación o nueva versión cuando las definiciones o la estructura cambien significativamente.
- Validación de pruebas y campos requeridos (por ejemplo, con una pequeña asignación) antes del despliegue completo.

*Ver:* [Crear una plantilla](../admin/create-template.md), [Editar una plantilla (Constructor de formularios)](../admin/edit-template.md)

### Gestión de usuarios y roles

- Asignar roles según la necesidad; Evita conceder en exceso (por ejemplo, solo el sistema de gestor para personal que requiere control total).
- Documentar la justificación de las subvenciones de acceso por rol y país para que las revisiones y auditorías de acceso sean sencillas.
- Utilizar el rastro de auditoría y el Panel de Seguridad para revisar acciones de alto riesgo (por ejemplo, eliminación de usuarios, cambios de rol).
- Revisar regularmente el **Panel de Gobernanza** para detectar acceso fantasma (usuarios inactivos con roles) y remediar rápidamente.
- Revisar usuarios con permisos de entidad pero sin rol RBAC — pueden necesitar asignar un rol o eliminar su acceso a la entidad.

*Ver:* [Roles y permisos de usuario](../admin/user-roles.md), [Gestionar usuarios](../admin/manage-users.md)

---

## Referencia rápida: Funciones de gobernanza en la plataforma

| Área | Característica | Referencia |
|------|---------|-----------|
| **Panel de Gobernanza** | Puntuación de salud, tira KPI, paneles de pilares, banderas | Panel de Administración → Gobernanza |
| **Propiedad de datos** | Propietario de la plantilla (por plantilla) | Panel de administración → Constructor de formularios → Plantilla de edición |
| **Propiedad de datos** | Propietario de datos (por asignación) | Panel de administración → Asignaciones → Crear/Editar |
| **Propiedad de datos** | Datos de la organización (FDS) | Este documento — [Propiedad de datos](#data-ownership) |
| Acceso | Roles (RBAC), asignación de país/entidad | [Roles y permisos de usuario](../admin/user-roles.md) |
| Acceso | Detección de acceso fantasma | Panel de control de → acceso de gobernanza |
| Acceso | Acciones permitidas por estatus | [Estado de envío y permisos](submission-statuses-and-permissions.md) |
| Calidad | Definiciones estándar | [Banco de Indicadores](../admin/indicator-bank.md) |
| Calidad | Validación, campos obligatorios | [Constructor de formularios (avanzado)](../admin/form-builder-advanced.md), [Editar plantilla](../admin/edit-template.md) |
| Calidad | Seguimiento atrasado con severidad | Panel de Gobernanza → Estándares de Calidad |
| Calidad | Revisión y aprobación | [Revisar y aprobar envíos](../admin/review-approve-submissions.md) |
| Rendición de cuentas | Registro de acciones de administrador, niveles de riesgo | [Niveles de riesgo de acción de administrador](../../workflows/admin/admin-action-risk-levels.md) |
| Rendición de cuentas | `submitted_by` / `approved_by` seguimiento | Cambios automáticos de estado |
| Rendición de cuentas | `activated_by` / `deactivated_by` seguimiento | Cambios automáticos en el ciclo de vida de la asignación |
| Cumplimiento | Tasa de cumplimiento de documentos FDRS | Panel de Gobernanza → Cumplimiento |
| Metadatos | Cobertura de definición de indicadores | Tablero de Gobernanza → Metadatos |
| Metadatos | Detección de sugerencias obsoletas | Tablero de Gobernanza → Metadatos |
| Ciclo de vida | Status, reabrir | [Estados de envío](submission-statuses-and-permissions.md), [Revisar y aprobar](../admin/review-approve-submissions.md) |
| Manejo seguro | Exportaciones | [Exportar y descargar datos](../admin/export-download-data.md) |
| Manejo seguro | URLs públicas | [Envíos de URL públicas](../admin/public-url-submissions.md) |
| Manejo seguro | Privacidad y sensibilidad | [Manejo de datos y privacidad](data-handling-and-privacy.md) |
| Operaciones | Ciclo de extremo a extremo | [Ejecutar un ciclo de reportes](../admin/run-a-reporting-cycle.md) |

---

## Campos de bases de datos que apoyan la gobernanza

Se añadieron los siguientes campos para apoyar la responsabilidad en la gobernanza:

### `AssignedForm` (nivel de asignación)

| Campo | Propósito |
|-------|---------|
| `data_owner_id` | Usuario responsable de la calidad de los datos durante este ciclo de recopilación |
| `activated_by_user_id` | Usuario que activó o reabrió la asignación |
| `deactivated_by_user_id` | Usuario que desactivó o cerró la asignación |

### `AssignmentEntityStatus` (estado por país dentro de una asignación)

| Campo | Propósito |
|-------|---------|
| `submitted_by_user_id` | Usuario que envió los datos para esta entidad |
| `approved_by_user_id` | Usuario que aprobó la publicación para esta entidad |

---

## Apéndice: Alineación con el ámbito de Microsoft

Para las organizaciones que utilizan o evalúan **Microsoft Purview**, el siguiente mapeo muestra cómo la estructura y el lenguaje de este documento se alinean con el marco de gobernanza de datos de Purview.

| Concepto de ámbito | Equivalente a un banco de datos humanitario |
|-----------------|----------------------------------|
| **Propietario de datos** (individuo o grupo responsable de gestionar un activo de datos) | **Propietario de la plantilla** (nivel de plantilla); **Propietario de Datos** (nivel de asignación); **FDS** (datos de la organización) |
| **Administrador de datos** (manteniendo la nomenclatura, los estándares de calidad de los datos y las reglas) | **Gerentes del Banco Indicador**; Administradores que definen validación y campos requeridos |
| **Glosario / Términos del glosario** (vocabulario y definiciones empresariales) | Banco de Indicadores como glosario empresarial de definiciones estándar de indicadores |
| **Dominio de gobernanza** (límite para gobernanza, propiedad, descubrimiento) | Límite de gobernanza a nivel de plataforma (datos de la organización, Banco de Indicadores) y alcance de asignación/entidad para los datos recogidos |
| **Control de acceso / RBAC** | Roles y permisos; asignación de país y entidad; controles de exportación; Detección de acceso fantasma |
| **Clasificación / Sensibilidad** (etiquetas de sensibilidad, tratamiento de datos sensibles) | gestión de datos y orientación sobre privacidad; Tratamiento de datos sensibles en envíos y exportaciones |
| **Pista de auditoría** | Registro de acciones administrativas con niveles de riesgo; `submitted_by` / `approved_by` / `activated_by` / `deactivated_by` atribución; Panel de seguridad para acciones de alto riesgo |
| **Calidad de los datos** (completitud, consistencia, conformidad, etc.) | Campos requeridos, reglas de validación, definiciones estándar, flujo de trabajo de envío y aprobación, seguimiento por retraso con buckets de severidad |
| **Flujo de trabajo** (validación y aprobación) | Estado de las presentaciones; aprueba; Reabrir |
| **Puntuación de salud / cumplimiento** | Puntuación de salud del Panel de Gobernanza (0–100) con puntuaciones de pilar ponderadas |

*Ver:* [Glosario de gobernanza de datos de Microsoft Purview](https://learn.microsoft.com/en-us/purview/data-governance-glossary), [Comienza con la gobernanza de datos en Microsoft Purview](https://learn.microsoft.com/en-us/purview/data-governance-get-started)

---

## Documentación relacionada

- [Manejo de datos y privacidad](data-handling-and-privacy.md) — Prácticas para envíos, exportaciones y URLs públicas
- [Cómo funciona la plataforma](../getting-started/how-it-works.md) — Plantillas, asignaciones y flujo de envío
- [Buscando ayuda](getting-help.md)
