# Sistema de IA: seguridad y privacidad

Este documento explica cómo funciona el asistente de IA de backoffice, qué datos pueden ser procesados por proveedores externos y qué controles técnicos existen para reducir la fuga accidental de información sensible.

## Alcance

- **En alcance**: chat de IA (`/api/ai/v1/*`), Base de conocimiento de IA / RAG, preguntas y respuestas de documentación de flujo de trabajo y los controles de seguridad que los rodean (DLP, limpieza de PII, eventos de auditoría).
- **Fuera de alcance**: seguridad general de la plataforma (autenticación, RBAC, copias de seguridad), excepto cuando afecta directamente al sistema de IA.

## Arquitectura de alto nivel

- **Frontend**: interfaz de chat (widget flotante + vista inmersiva) en `app/static/js/chatbot/` (módulos ES; diálogo DLP en `dlp-policy.js`).
- **Backend**: Endpoints de Flask API para chat de IA en `app/routes/ai.py` (HTTP + SSE) y `app/routes/ai_ws.py` (WebSocket).
- **Orquestación**: `app/services/ai/chat/engine.py` gestiona el flujo de chat (historial, recuperación, llamadas al proveedor).
- **Proveedores**: LLMs/embeddings externos (por ejemplo, OpenAI/Gemini/Azure OpenAI según el entorno) más componentes locales opcionales.

## Qué datos pueden enviarse a proveedores externos

Dependiendo del tipo de solicitud y las funciones habilitadas, el backend puede enviar alguna combinación de:

- **Texto de mensaje de usuario**
- **Historial de conversaciones** (mensajes recientes, según sea necesario para la continuidad)
- **Contexto de página sanitizado** (Estado/contexto de la interfaz para ayudar al asistente; se eliminan algunos campos de alto riesgo)
- **Fragmentos de documento/flujo de trabajo recuperados** (para respuestas RAG)

Importante: algunas funciones de IA requieren llamadas externas a API (por ejemplo, completar chats, reescribir consultas, embeddings), por lo que **evitar que se envíen datos sensibles** es un objetivo principal de seguridad.

## Controles básicos de privacidad/seguridad

### 1) Prevención de Pérdida de Datos (DLP) protege los mensajes salientes

Antes de que un mensaje pueda enviarse a un proveedor externo de IA, el backend ejecuta un escaneo DLP de mejor esfuerzo (basado en regex) para detectar patrones sensibles comunes, como:

- correos electrónicos, números de teléfono
- JWTs / tokens Bearer / credenciales Basic auth
- claves privadas (cualquier bloque de clave privada PEM o PGP, incluido un bloque pegado sin su línea END)
- contraseñas / frases de contraseña, secretos / claves API — como asignaciones `clave: valor` o `CLAVE=valor` (archivos env, JSON, YAML, cadenas de conexión como `AccountKey=`), contraseñas en URL de conexión (`postgres://…@host` con contraseña integrada) y formatos conocidos de claves de proveedores (por ejemplo OpenAI `sk-…`, AWS `AKIA…`, GitHub `ghp_…`)
- IBANs (con dígitos de control validados) y números de tarjetas de pago (validación Luhn) para reducir falsos positivos

La detección de teléfonos omite las formas numéricas habituales en preguntas sobre datos: listas de años, cifras grandes o agrupadas por miles, fechas, direcciones IP y columnas de tablas.

**Experiencia de usuario**

- Un mensaje nunca se envía ni se guarda con un valor detectado: cuando pasa, cada valor se sustituye por un marcador como `[REDACTED_EMAIL]`.
- En el modo `confirm` (predeterminado), los correos electrónicos y números de teléfono se enmascaran automáticamente (configurable). Las credenciales, claves e identificadores financieros abren un diálogo: **Enmascarar y enviar** envía el mensaje enmascarado, **Cancelar** devuelve el mensaje al usuario para editarlo y no guarda nada.
- En el modo `block`, el mensaje se rechaza sea cual sea su contenido; el diálogo solo ofrece editarlo.
- Los clientes Website y móvil reciben un error que indica lo detectado (por ejemplo "Sensitive information detected (password). Remove it and send your message again.").
- Los mensajes del panel de IA del constructor de formularios conservan sus direcciones de correo y números de teléfono (los cuestionarios importados los contienen legítimamente), pero se analizan para todos los demás tipos.

**Implementación**

- Lógica DLP: `app/services/ai/chat/dlp.py` (`screen_ai_message`, `evaluate_ai_message`, `mask_sensitive_text`, `mask_conversation_history`)
- DLP se aplica de forma consistente entre los transportes:
  - Chat HTTP JSON
  - Transmisión SSE
  - Transmisión en WebSocket
- El historial de conversación que envía el cliente (edición o reintento de un mensaje anterior, chat anónimo) se enmascara en el servidor antes de guardarse o enviarse a un proveedor.

**Configuración**

DLP se configura directamente en código (no en variables de entorno):

- `Backoffice/config/config.py`
  - `AI_DLP_ENABLED`
  - `AI_DLP_MODE`: `warn` (enmascarar todo y enviar), `confirm` (predeterminado; ver arriba), `block`
  - `AI_DLP_AUTO_MASK_KINDS`: tipos que el modo `confirm` enmascara sin preguntar (predeterminado: `email`, `phone`)
  - `AI_DLP_MAX_SCAN_CHARS`

### 2) Limpieza / redacción de la información personal antes de llamadas externas

Además del DLP (que puede detener una solicitud), el sistema también aplica **filtrado de PII** (redacción) para reducir la exposición cuando el contenido debe enviarse externamente (por ejemplo, para ayudar al modelo a responder). El filtrado usa los mismos patrones que el DLP, además de tokens opacos largos.

El filtrado se aplica a:

- texto de mensajes de usuario
- los mensajes del usuario en el historial de conversación (las respuestas del asistente son la propia salida del modelo y se envían tal cual)
- Contexto de página (recursivamente)
- algunas entradas y registros que reescriben consultas

Las solicitudes del panel de IA del constructor de formularios omiten este filtrado para que el texto de los cuestionarios importados se reproduzca fielmente; el DLP sigue analizándolas en busca de credenciales e identificadores financieros.

Implementación:

- `app/services/ai/providers/formatting.py`: `scrub_pii_text`, `scrub_pii_context`
- `app/services/ai/chat/engine.py`: aplica el filtrado antes de las llamadas al proveedor

### 3) Minimización del contexto de la página

El frontend puede enviar contexto de página para ayudar a responder preguntas relacionadas con la interfaz. El backend limpia y elimina estos datos e elimina intencionadamente campos de alto riesgo (por ejemplo, URLs o grandes blobs en bruto) para reducir fugas accidentales.

Implementación:

- `app/utils/ai/ai_utils.py`: ayudantes compartidos como la sanitización del contexto
- `app/services/ai/providers/formatting.py`: limpieza recursiva de contexto

### 4) Auditoría del registro para eventos DLP (sin almacenar contenido de mensajes)

Cuando DLP detecta patrones sensibles, el backend escribe un **evento de auditoría de seguridad** para que los administradores puedan monitorizar con qué frecuencia se activa el guardia y responder a comportamientos de riesgo.

Propiedades de seguridad:

- El evento de auditoría **no almacena el mensaje del usuario**.
- Almacena solo **recuentos y tipos** de hallazgos (por ejemplo, `{"kind":"jwt","count":1}`), más metadatos como transporte, punto final e identificadores.
- `context_data.action` registra lo ocurrido: `auto_masked` (enmascarado y enviado sin preguntar), `confirm_required` (se mostró el diálogo), `sent_masked` (el usuario eligió Enmascarar y enviar) o `blocked`.
- La gravedad es `high` para credenciales, claves e identificadores financieros cuando se detuvo al usuario o este eligió enviar, y `medium` cuando se enmascararon automáticamente (por ejemplo en el modo `warn`). Los datos de contacto son `medium` y `low` con el mismo criterio.

Implementación:

- `app/services/ai/chat/dlp.py`: `log_dlp_audit_event`
- Modelo: `app/models/system.py` (`SecurityEvent`, `context_data` JSON)
- Interfaz de administración:
  - Panel de seguridad: `/admin/security/dashboard`
  - Lista de eventos de seguridad: `/admin/security/events`

Para filtrar eventos DLP de IA, busca:

- `event_type = "ai_dlp_sensitive_detected"`

### 5) Autenticación y control de acceso

- Los endpoints de IA están protegidos por los mismos mecanismos de autenticación de Backoffice (inicio de sesión basado en sesión y flujos de tokens portadores cuando corresponda).
- Las páginas solo para administradores (paneles de seguridad/eventos) requieren permisos apropiados (véase `app/routes/admin/security_dashboard.py`).

## Guía operativa (administradores)

### Política recomendada

- Tratar al asistente de IA como **no confiable para datos sensibles**.
- Animar a los usuarios a:
  - evitar enviar credenciales, tokens, claves privadas y datos personales
  - reemplazar identificadores reales por marcadores de posición al solicitar ayuda (por ejemplo, "<TOKEN>", "<EMAIL>")

### Gestionando un pico o incidente DLP

1. Revisa los eventos de seguridad recientes bajo `/admin/security/events` y filtra por `ai_dlp_sensitive_detected`.
2. Revisa los metadatos en `context_data` para detectar patrones (transporte, cliente, frecuencia, cuentas afectadas).
3. Considera apretar temporalmente el modo DLP a `block` en `Backoffice/config/config.py` y volver a desplegarlo si es necesario.
4. Si se han expuesto secretos, rotar las credenciales (claves API, tokens) y revisar los registros de acceso.

## Limitaciones y expectativas

- DLP es **mejor esfuerzo** y basado en patrones; Puede pasar por alto contenido sensible y también puede producir falsos positivos.
- El scrubbing de la PII también es el mejor esfuerzo; Reduce el riesgo pero no garantiza la eliminación completa.
- La salida de la IA puede ser incorrecta; los usuarios deben verificar información importante (la interfaz advierte sobre esto).

## Ubicaciones de códigos de teclas (referencia)

| Área | Camino |
|------|------|
| Endpoints de chat de IA (HTTP + SSE) | `app/routes/ai.py` |
| Endpoint de chat de IA (WebSocket) | `app/routes/ai_ws.py` |
| Orquestación por chat | `app/services/ai/chat/engine.py` |
| DLP guardia + eventos de auditoría | `app/services/ai/chat/dlp.py` |
| Diálogo DLP (interfaz de chat) | `app/static/js/chatbot/dlp-policy.js` |
| Ayudantes de limpieza de información personal | `app/services/ai/providers/formatting.py` |
| Modelo de eventos de seguridad | `app/models/system.py` |
| Páginas de seguridad de administrador | `app/routes/admin/security_dashboard.py` |

## Documentación relacionada

- [Política de Uso de IA](../common/ai-use-policy.md) — Política orientada al usuario (uso aceptable, responsabilidades)
- [Chatbot de IA](../common/ai-chatbot.md) — Uso del chatbot, niveles de acceso, RBAC y privacidad documental
- [Base de conocimientos de IA e incrustaciones](ai-document-library-and-embeddings.md)
- [Manejo de datos y privacidad](../../data-reporting/data-handling-and-privacy.md)

