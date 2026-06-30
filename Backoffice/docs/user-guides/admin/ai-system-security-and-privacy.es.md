# Sistema de IA: seguridad y privacidad

Este documento explica cómo funciona el asistente de IA de backoffice, qué datos pueden ser procesados por proveedores externos y qué controles técnicos existen para reducir la fuga accidental de información sensible.

## Alcance

- **En alcance**: chat de IA (`/api/ai/v2/*`), Biblioteca de Documentos de IA / RAG, preguntas y respuestas de documentación de flujo de trabajo y los controles de seguridad que los rodean (DLP, limpieza de PII, eventos de auditoría).
- **Fuera de alcance**: seguridad general de la plataforma (autenticación, RBAC, copias de seguridad), excepto cuando afecta directamente al sistema de IA.

## Arquitectura de alto nivel

- **Frontend**: interfaz de chat (widget flotante + vista inmersiva) en `app/static/js/chatbot.js`.
- **Backend**: Endpoints de Flask API para chat de IA en `app/routes/ai.py` (HTTP + SSE) y `app/routes/ai_ws.py` (WebSocket).
- **Orquestación**: `app/services/ai_chat_engine.py` gestiona el flujo de chat (historial, recuperación, llamadas al proveedor).
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
- JWTs / Fichas portadoras
- claves privadas
- contraseñas / secretos / claves API
- IBANs y números de tarjetas de pago (con el cheque Luhn para reducir falsos positivos)

**Experiencia de usuario**

- Si se detectan patrones sensibles, el asistente puede requerir **confirmación del usuario** ("Enviar de todos modos") o **bloquear** el mensaje dependiendo de la configuración.
- La interfaz explica el riesgo y fomenta la eliminación del texto sensible.

**Implementación**

- Lógica DLP: `app/services/ai_dlp.py` (`analyze_text`, `evaluate_ai_message`)
- DLP se aplica de forma consistente entre los transportes:
  - Chat HTTP JSON
  - Transmisión SSE
  - Transmisión en WebSocket

**Configuración**

DLP se configura directamente en código (no en variables de entorno):

- `Backoffice/config/config.py`
  - `AI_DLP_ENABLED`
  - `AI_DLP_MODE` (valores típicos: `warn`, `confirm`, `block`)
  - `AI_DLP_MAX_SCAN_CHARS`

### 2) Limpieza / redacción de la información personal antes de llamadas externas

Además del DLP (que puede detener una solicitud), el sistema también aplica **filtrado de PII** (redacción) para reducir la exposición cuando el contenido debe enviarse externamente (por ejemplo, para ayudar al modelo a responder).

El fregado se aplica a:

- texto de mensajes de usuario
- Fragmentos de historial de conversaciones
- Contexto de página (recursivamente)
- algunas entradas y registros que reescriben consultas

Implementación:

- `app/services/ai_providers.py`: `scrub_pii_text`, `scrub_pii_context`
- `app/services/ai_chat_engine.py`: aplica el scrubbing antes de que el proveedor llame

### 3) Minimización del contexto de la página

El frontend puede enviar contexto de página para ayudar a responder preguntas relacionadas con la interfaz. El backend limpia y elimina estos datos e elimina intencionadamente campos de alto riesgo (por ejemplo, URLs o grandes blobs en bruto) para reducir fugas accidentales.

Implementación:

- `app/utils/ai_utils.py`: ayudantes compartidos como la sanitización del contexto
- `app/services/ai_providers.py`: limpieza recursiva de contexto

### 4) Auditoría del registro para eventos DLP (sin almacenar contenido de mensajes)

Cuando DLP detecta patrones sensibles, el backend escribe un **evento de auditoría de seguridad** para que los administradores puedan monitorizar con qué frecuencia se activa el guardia y responder a comportamientos de riesgo.

Propiedades de seguridad:

- El evento de auditoría **no almacena el mensaje del usuario**.
- Almacena solo **recuentos y tipos** de hallazgos (por ejemplo, `{"kind":"jwt","count":1}`), más metadatos como transporte, punto final e identificadores.

Implementación:

- `app/services/ai_dlp.py`: `log_dlp_audit_event`
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
| Orquestación por chat | `app/services/ai_chat_engine.py` |
| DLP guardia + eventos de auditoría | `app/services/ai_dlp.py` |
| Ayudantes de limpieza de información personal | `app/services/ai_providers.py` |
| Modelo de eventos de seguridad | `app/models/system.py` |
| Páginas de seguridad de administrador | `app/routes/admin/security_dashboard.py` |

## Documentación relacionada

- [Política de Uso de IA](../common/ai-use-policy.md) — Política orientada al usuario (uso aceptable, responsabilidades)
- [Chatbot de IA](../common/ai-chatbot.md) — Uso del chatbot, niveles de acceso, RBAC y privacidad documental
- [Biblioteca de documentos de IA e incrustaciones](ai-document-library-and-embeddings.md)
- [Manejo de datos y privacidad](../../data-reporting/data-handling-and-privacy.md)

