# Chatbot de IA

Esta guía explica cómo utilizar el chatbot de IA, qué puede hacer, cómo funcionan los accesos y permisos, y cómo los controles de privacidad de documentos afectan a lo que el asistente puede encontrar y consultar.

## Resumen

El chatbot de IA es un asistente integrado en el Backoffice que puede responder preguntas sobre tus datos, buscar en documentos subidos y ayudarte a navegar por la plataforma. Está disponible como un **widget flotante** en la mayoría de las páginas y como una **vista inmersiva a pantalla completa** para conversaciones más largas.

El chatbot utiliza Generación Aumentada por Recuperación (RAG): cuando haces una pregunta, puede buscar en el Banco de Datos, documentos subidos y guías de flujo de trabajo, y luego usar esos resultados como contexto para su respuesta.

## Antes de empezar

- Necesitas una cuenta en el Backoffice para usar el chatbot. El acceso anónimo es limitado (véase [Niveles de acceso](#access-levels) más abajo).
- El chatbot requiere que al menos un proveedor de IA esté configurado por tu administrador (por ejemplo, OpenAI, Gemini o Azure OpenAI).
- Las respuestas de la IA pueden ser incorrectas. Verifica siempre la información importante.

---

## Uso del chatbot

### Iniciar una conversación

1. Abre el widget del chatbot haciendo clic en el icono de chat en la esquina inferior derecha de cualquier página, o navega a la **vista inmersiva a pantalla completa** desde el panel de control.
2. Escribe tu pregunta en el campo de entrada y pulsa **Enviar** (o pulsa Enter).
3. El asistente procesará tu pregunta — puede que veas un indicador de "pensando" mientras recupera datos o busca en documentos.

### Prompts rápidos

La vista inmersiva ofrece ejemplos de prompts para ayudarte a empezar:

- "¿Cuántos voluntarios hay en Bangladés?"
- "Voluntarios en Siria a lo largo del tiempo"
- "Mapa de calor mundial de voluntarios por país"
- "Número de sucursales en Kenia"
- "Estado mayor y unidades locales en Nigeria"

### Gestión de conversaciones

- **Nuevo chat** — Inicia una conversación nueva en cualquier momento.
- **Buscar** — Encuentra conversaciones anteriores por palabra clave.
- **Eliminar** — Elimina una sola conversación o borra todas las conversaciones. La eliminación es permanente.

### Controles de fuente de datos

El área de entrada incluye un botón de **fuentes de datos** (icono deslizante) que te permite elegir qué fuentes busca el asistente:

| Fuente | Lo que incluye |
|--------|-----------------|
| **Banco de datos** | Valores de los indicadores, datos de países y envíos de formularios almacenados en la plataforma |
| **Documentos del sistema** | Documentos subidos a la Biblioteca de Documentos de IA por administradores |
| **Documentos de la UPR** | Documentos de Planificación y Reporte Unificados |

Puedes activar o desactivar cada fuente por mensaje. Desactivar una fuente significa que el asistente no buscará ni recuperará esa solicitud.

### Edición y reintentos

- **Edita** un mensaje enviado para reformular tu pregunta. El asistente regenerará su respuesta a partir del texto editado.
- **Reintentar** una respuesta de asistente si la respuesta no fue satisfactoria.
- **Copia** cualquier respuesta de asistente a tu portapapeles.

### Retroalimentación

Utiliza los botones de 'Me gusta** y 'No me gusta** en cualquier mensaje del asistente para dar feedback. Esto ayuda a los administradores a monitorizar la calidad y mejorar el sistema.

---

## Niveles y roles de acceso (RBAC)

El chatbot respeta el control de acceso basado en roles de la plataforma. Tu puesto determina qué datos puede acceder el asistente en tu nombre.

### Niveles de acceso

| Nivel de acceso | ¿Quién | Capacidades de chatbots |
|--------------|-----|---------------------|
| **Gestor del sistema** | Administrador a nivel de plataforma | Acceso completo a todos los datos, documentos, países y herramientas. Exenta de límites de tarifa diaria por usuario. |
| **Admin** | Administrador de organizaciones | Acceso total a todos los datos, documentos y países. Se aplican los límites estándar de tarifa. |
| **Usuario** (punto focal, solo vista, etc.) | Usuario autenticado habitual | El acceso está limitado a los países asignados. Documentos filtrados por configuración de privacidad (ver más abajo). Se aplican los límites estándar de tarifa. |
| **Público** (anónimo) | Visitante no autenticado a través de la web | Solo documentos públicos visibles. Sin persistencia en la conversación. Límites de tarifas más estrictos. |

### Qué puede ver cada rol a través del chatbot

#### Gestor de sistemas y administrador

- Todos los datos de los indicadores para todos los países
- Todos los documentos independientemente de la configuración de privacidad
- Todas las plantillas de formularios, asignaciones y envíos
- Estadísticas del sistema e información del usuario
- Todas las guías de flujo de trabajo

#### Focal Point y otros usuarios autenticados

- Datos indicadores solo para **países asignados** — el asistente no devolverá datos de los países a los que no estás asignado
- Documentos marcados como **públicos**, documentos que **posees** y documentos cuyo rol está incluido en la lista de **roles permitidos** del documento
- Asignaciones y entregas para los países asignados
- Guías de flujo de trabajo disponibles para tu puesto

#### Usuarios anónimos / Públicos

- Solo documentos marcados explícitamente como **público** (y sin restricción de rol, o con `public` en la lista de roles permitidos)
- Datos generales de indicadores (no asignados a asignaciones específicas)
- No persistencia en conversaciones — el historial solo existe en la sesión del navegador

### Los permisos pasaron a la asistente

Cuando envías un mensaje, el sistema construye un **contexto de acceso** que incluye:

- Tu rol y nivel de acceso
- Tus identificadores de país asignados (si procede)
- Un conjunto de banderas de permiso (por ejemplo, si puedes ver plantillas, asignaciones, documentos, usuarios)

Este contexto viaja con cada petición, por lo que el asistente y sus herramientas hacen cumplir los mismos límites que el resto de la plataforma. El asistente no puede eludir tus permisos — si no puedes ver ciertos datos en la interfaz de Backoffice, el asistente tampoco podrá verlos.

---

## Privacidad documental

Los documentos en la Biblioteca de Documentos de IA tienen controles de privacidad que determinan quién puede encontrarlos a través del chatbot. Estos controles los establecen los administradores al subir o gestionar documentos.

### Campos de privacidad

Cada documento tiene dos ajustes de visibilidad:

| Campo | Valores | Efecto |
|-------|--------|--------|
| **Público** (`is_public`) | Sí / No | Si **Sí**, el documento es visible para todos los usuarios (incluidos los visitantes anónimos), sujeto al filtro de roles permitidos. Si **No**, solo el propietario del documento, los usuarios cuyo rol coincide con `allowed_roles` y los administradores pueden verlo. |
| **Roles permitidos** (`allowed_roles`) | Una lista de roles, o vacío | Si **vacío** (nulo), cualquier usuario que pase la comprobación pública/de propiedad puede ver el documento. Si se establece (por ejemplo, `admin`, `focal_point`), solo los usuarios con un rol coincidente (más el propietario y los administradores) pueden verlo. |

### Visibilidad efectiva por combinación

| `is_public` | `allowed_roles` | ¿Quién puede encontrar este documento |
|-------------|-----------------|---------------------------|
| Sí | Vacío | Todos, incluidos los usuarios anónimos |
| Sí | `[admin, focal_point]` | Usuarios anónimos y cualquier usuario autenticado cuyo rol esté en la lista (más administradores/gestores de sistema) |
| No | Vacío | Propietario del documento + solo administradores/gestores de sistemas |
| No | `[focal_point]` | Propietario del documento + puntos focales + administradores/gestores de sistemas |

**Reglas clave:**

- **Los administradores y gestores de sistemas siempre ven todos los documentos**, independientemente de la configuración de privacidad.
- **Los propietarios de documentos siempre ven sus propios documentos**, independientemente de la configuración de privacidad.
- **Los usuarios anónimos** solo ven documentos donde `is_public = Yes` y bien `allowed_roles` está vacío o incluye a `public`.

### Cómo afecta la privacidad a las respuestas de los chatbots

Cuando haces una pregunta que involucre la búsqueda de documentos, el asistente ejecuta una búsqueda de similitud (vectorial o híbrida) contra la Biblioteca de Documentos de IA. Antes de devolver los resultados, el sistema aplica un **filtro de permisos** que hace cumplir las reglas anteriores. Los documentos que no está autorizado a ver quedan completamente excluidos de los resultados de búsqueda: el asistente no citará, resumirá ni referenciará contenido de documentos fuera de su alcance.

Esto significa que dos usuarios que hacen la misma pregunta pueden recibir respuestas diferentes si tienen acceso a conjuntos distintos de documentos.

---

## Qué puede hacer el asistente (herramientas)

El chatbot tiene acceso a un conjunto de herramientas que puede usar para responder a tus preguntas. Estas herramientas consultan datos en tiempo real de la plataforma: no dependen únicamente de conocimientos preentrenados.

### Herramientas de recuperación de datos

| Herramienta | Qué hace |
|------|-------------|
| **Obtener valor indicador** | Recupera un valor indicador específico para un país y periodo |
| **Obtener serie temporal indicadora** | Recupera valores históricos de un indicador a lo largo de varios años |
| **Obtener metadatos de indicadores** | Devuelve la definición, la unidad y otros detalles sobre un indicador |
| **Obtener valores indicadores para todos los países** | Recupera un indicador específico en todos los países (útil para comparaciones y mapas) |
| **Obtener información del país** | Retorna detalles sobre un país (Sociedad Nacional, región, etc.) |
| **Comparar países** | Comparación lado a lado de varios países en indicadores seleccionados |

### Herramientas de formularios y asignaciones

| Herramienta | Qué hace |
|------|-------------|
| **Obtener valor del campo de formulario** | Recupera un valor específico de campo de una presentación de formulario |
| **Obtener valores indicadores de asignación** | Recupera valores indicadores de una asignación específica |
| **Obtén asignaciones de usuarios** | Lista tus asignaciones (o todas las asignaciones para administradores) |
| **Obtén detalles de la plantilla** | Devuelve la estructura y los campos de una plantilla de formulario |

### Herramientas de búsqueda de documentos

| Herramienta | Qué hace |
|------|-------------|
| **Documentos de lista** | Lista documentos disponibles (filtrados por tus permisos) |
| **Buscar en documentos** | Búsqueda semántica (vectorial) en el contenido del documento |
| **Buscar documentos (híbrido)** | Búsqueda combinada de palabra clave + semántica para mejor recuerdo |

### Herramientas UPR

| Herramienta | Qué hace |
|------|-------------|
| **Obtén el valor del KPI UPR** | Recupera un valor de KPI de Planificación y Reporte Unificado |
| **Obtén series temporales KPI UPR** | Valores históricos de KPI de la UPR a lo largo del tiempo |
| **Obtén los valores de KPI UPR para todos los países** | Valores de KPI UPR en todos los países |
| **Analizar áreas de enfoque de planes unificados** | Analiza áreas de enfoque en planes unificados |

### Flujo de trabajo y herramientas del sistema

| Herramienta | Qué hace |
|------|-------------|
| **Consulta la guía de flujo de trabajo** | Recupera una guía de flujo de trabajo paso a paso (filtrada por tu puesto) |
| **Buscar documentación de flujo de trabajo** | Busca documentación de flujo de trabajo (filtrada por tu puesto) |
| **Validar según las directrices** | Valida los datos en relación con las directrices de la plataforma |
| **Obtener información de usuario actual** | Información de devolución sobre tu cuenta y permisos |
| **Obtén estadísticas del sistema** | Estadísticas a nivel de plataforma (solo administrativo) |

Todas las herramientas respetan tu nivel de acceso. Por ejemplo, las herramientas de recuperación de datos solo devolverán datos de los países a los que estés asignado (a menos que seas administrador), y las herramientas de documentos solo devolverán documentos que estés autorizado a ver.

---

## Límites de tasas

Para garantizar el uso justo y la estabilidad del sistema, el chatbot aplica límites de tasa:

| Límite | Usuarios autenticados | Gestores de sistemas | Anónimo |
|-------|-------------------|-----------------|-----------|
| **Por minuto** | 120 solicitudes | 120 solicitudes | 60 solicitudes |
| **Por día (usuario)** | 1.000.000 | Exento | N/A |
| **Por día (a nivel de sistema)** | 5.000.000 en total entre todos los usuarios | — | — |

Si alcanzas un límite de tarifa, espera un momento antes de enviar otro mensaje. El límite se reinicia después de la ventana temporal correspondiente.

---

## Avisos de privacidad y seguridad

El chatbot muestra dos avisos importantes:

1. **"No compartas información sensible." ** — El sistema envía tus mensajes a proveedores de IA externos para su procesamiento. Evita incluir contraseñas, tokens, claves API, datos personales u otras credenciales.
2. **"La IA puede cometer errores. Revisa información importante." ** — Las respuestas generadas por IA pueden ser inexactas. Verifica siempre los datos críticos con la fuente.

### Protecciones integradas

La plataforma incluye varias capas de protección para reducir la exposición accidental de información sensible:

- **Prevención de Pérdida de Datos (DLP)** — Los mensajes salientes se escanean en busca de patrones sensibles comunes (correos electrónicos, tokens, claves, números de tarjeta). Dependiendo de la configuración, el sistema puede avisarte, pedir confirmación o bloquear el mensaje.
- **Limpieza de PII** — Antes de que el contenido se envíe a proveedores externos, el sistema elimina información personal identificable detectada.
- **Minimización del contexto de la página** — Cuando el chatbot envía el contexto de la página para ayudar a responder preguntas relacionadas con la interfaz, se eliminan campos de alto riesgo (como las URLs).

Para un resumen de uso aceptable y salvaguardas, consulte la [Política de Uso de IA](ai-use-policy.md). Pregunta a tu administrador si necesitas más detalles sobre cómo están configurados los controles de seguridad.

---

## Consejos

- **Sé específico** — Incluye el país, el indicador y el periodo de tiempo en tu pregunta para obtener respuestas más precisas.
- **Usar controles de fuente de datos** — Si solo quieres respuestas de documentos subidos, desactiva la fuente del Banco de Datos (y viceversa).
- **Comprobar la fuente** — Cuando el asistente haga referencia al contenido del documento, verifica la información con el documento original.
- **Utiliza la vista inmersiva** para conversaciones analíticas largas — el formato a pantalla completa es mejor para leer gráficos, tablas y respuestas detalladas.
- **Exportar conversaciones importantes** antes de limpiarlas — la eliminación es permanente.

## Problemas comunes

| Problema | Qué comprobar |
|---------|--------------|
| El chatbot no está disponible | Pregunta a tu administrador si un proveedor de IA está configurado y habilitado. |
| Error "No provider configurado" | Al menos una clave de proveedor de IA (OpenAI, Gemini o Azure) debe estar configurada en el entorno. |
| Assistant cannot find a document I uploaded | Check the document’s privacy settings on the assignment or form (whether it is marked searchable) and whether processing has finished. If it should be searchable and still does not appear, ask your administrator. |
| El asistente devuelve datos del país equivocado | Reformula tu pregunta con el nombre completo del país. Comprueba que estás asignado a ese país. |
| Límite de tasa alcanzado | Espera un minuto e inténtalo de nuevo. Si el problema persiste, contacta con tu administrador. |
| Advertencia DLP en mi mensaje | El sistema detectó un patrón que parece datos sensibles. Elimina o reemplaza el contenido sensible y reenvía. |
| Falta el historial de conversaciones | Si usas el modo público/anónimo, las conversaciones no se guardan. Inicia sesión para mantener las conversaciones. |

## Relacionado

- [Política de Uso de IA](ai-use-policy.md) — Uso aceptable, manejo de datos y responsabilidades
- [Manejo de datos y privacidad](data-handling-and-privacy.md) — Orientación básica para manejar y compartir datos de forma segura
