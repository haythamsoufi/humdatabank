# Biblioteca de documentos de IA e incrustaciones

Este documento describe cómo funciona la Biblioteca de Documentos de IA: cómo se procesan los documentos, cómo se generan los embeddings (vectores) y cómo se utilizan para la búsqueda semántica y la generación aumentada por recuperación (RAG).

## Resumen

La Biblioteca de Documentos de IA permite a los administradores subir documentos (PDF, Word, etc.) para que el chatbot y las herramientas de IA puedan responder preguntas usando ese contenido. Los documentos son:

1. **Extracted** — se extraen texto, páginas, secciones y, opcionalmente, tablas del archivo.
2. **Chunked** — divididos en bloques de texto más pequeños para contexto y límites de tokens.
3. **Embebido** — cada bloque se convierte en un vector (incrustación) mediante un modelo de incrustación.
4. **Almacenados** — los vectores se almacenan en la base de datos (pgvector) y se vinculan a fragmentos.

Cuando un usuario hace una pregunta, la consulta se integra con el mismo modelo, y el sistema encuentra los fragmentos más similares (búsqueda vectorial o híbrida) y los utiliza como contexto para la respuesta.

## Pipeline de procesamiento de documentos

El procesamiento se ejecuta cuando tú:

- **Subir** un documento a la página de la Biblioteca de Documentos de IA (`/admin/ai/documents`).
- **Procesar documentos seleccionados** importados del sistema de gestión documental.
- **Reprocesar** un documento existente (re-extraer, volver a fragmentar, volver a incrustar).

Pasos de la tubería (véase `app/routes/ai_documents.py`, `_process_document_sync`):

| Paso | ¿Qué pasa |
|------|----------------|
| **1. Extract** | `AIDocumentProcessor` lee el archivo y extrae texto, límites de página, secciones y (opcionalmente) tablas. |
| **2. Chunk** | `AIChunkingService` divide el texto en fragmentos (por defecto: fragmentación semántica, ~512 tokens por chunk, solapamiento de 50 tokens). Opcional: bloques de tabla y bloques visuales UPR. |
| **3. Generar incrustaciones** | Solo si el documento está marcado como buscable*. `AIEmbeddingService` convierte el texto de cada fragmento en un vector (véase [Proveedores de incrustación](#embedding-providers) más abajo). |
| **4. Tienda** | `AIVectorStore` guarda cada vector en la tabla `AIEmbedding` (pgvector), enlazada al `AIDocumentChunk` correspondiente. |

Los registros de fragmentos (`AIDocumentChunk`) siempre se crean; Las incrustaciones solo se crean cuando el documento es buscable.

## Proveedores de integración

Las incrustaciones se generan por `app/services/ai_embedding_service.py`. Se soportan dos proveedores.

### OpenAI (por defecto)

- **Proveedor:** `AI_EMBEDDING_PROVIDER=openai` (por defecto).
- **Model:** `AI_EMBEDDING_MODEL` — por defecto `text-embedding-3-small`.
- **Dimensiones:** `AI_EMBEDDING_DIMENSIONS` — por defecto `1536` (debe coincidir con la columna pgvector).
- **Dónde se ejecuta:** En **los servidores de OpenAI**. Tu aplicación envía texto en bloques a la API de OpenAI y recibe vectores. Necesitas `OPENAI_API_KEY` establecido.
- **Coste:** Facturado por token por OpenAI (por ejemplo, text-embedding-3-small es bajo coste por 1M de tokens).

Así que **`text-embedding-3-small` no se ejecuta localmente** — se utiliza a través de la API de OpenAI.

### Local (Transformers de Frase)

- **Proveedor:** `AI_EMBEDDING_PROVIDER=local`.
- **Modelo:** `all-MiniLM-L6-v2` (fijado en el servicio) — 384 dimensiones.
- **Donde se ejecuta:** **En tu máquina**. La aplicación carga el modelo con la biblioteca `sentence_transformers`; no se llama a ninguna API externa.
- **Coste:** No hay coste por ficha; requiere `pip install sentence-transformers` y suficiente RAM/CPU.

Si usas incrustaciones locales debes:

- Set `AI_EMBEDDING_DIMENSIONS=384`.
- Asegurarse de que la columna pgvector de la base de datos tenga 384 dimensiones (puede ser necesaria la migración). El esquema por defecto es 1536 para OpenAI.

## Referencia de configuración

| Variable | Predeterminado | Descripción |
|----------|---------|-------------|
| `AI_EMBEDDING_PROVIDER` | `openai` | `openai` o `local`. |
| `AI_EMBEDDING_MODEL` | `text-embedding-3-small` | Nombre del modelo (solo OpenAI; ignorado por `local`). |
| `AI_EMBEDDING_DIMENSIONS` | `1536` | Tamaño vectorial. Debe coincidir con la columna de base de datos y el modelo (1536 para text-embedding-3-small, 384 para todo MiniLM-L6-v2). |
| `OPENAI_API_KEY` | — | Requerida cuando `AI_EMBEDDING_PROVIDER=openai`. |
| `AI_CHUNK_SIZE` | `512` | Apunta al tamaño del fragmento en fichas. |
| `AI_CHUNK_OVERLAP` | `50` | Solapamiento entre bloques consecutivos (tokens). |
| `AI_MAX_DOCUMENT_SIZE_MB` | `50` | Tamaño máximo de archivo para procesar. |
| `AI_TOP_K_RESULTS` | `5` | Número de trozos devueltos para búsqueda. |

Consulta `Backoffice/config/config.py` para la sección completa de IA/RAG y cualquier opción adicional.

## Cómo se usan los vectores

- **Búsqueda vectorial:** La consulta de usuario está integrada con el mismo servicio de incrustación; La aplicación ejecuta una búsqueda de similitud (por ejemplo, coseno) en PGVECTOR y devuelve los primeros k bloques.
- **Búsqueda híbrida:** Combina similitud vectorial y búsqueda por palabras clave para mejorar la memoria.
- **RAG:** Los fragmentos recuperados se pasan como contexto al LLM al responder preguntas (chatbot, preguntas y respuestas de la biblioteca de documentos de IA, documentos de flujo de trabajo).

La página de la Biblioteca de Documentos de IA te permite elegir **Solo vector** o **Híbrido (palabras clave e incrustaciones)** para la función "Preguntar".

## Ubicaciones de códigos de teclas

| Componente | Camino |
|-----------|------|
| Pipeline de procesamiento de documentos | `app/routes/ai_documents.py` — `_process_document_sync` |
| Fragmentación | `app/services/ai_chunking_service.py` |
| Generación incrustada | `app/services/ai_embedding_service.py` |
| Almacenamiento vectorial y búsqueda | `app/services/ai_vector_store.py` |
| UI de la Biblioteca de Documentos de IA | `app/templates/admin/ai/documents.html` |

## Documentación relacionada

- [Chatbot de IA](../common/ai-chatbot.md) — Uso del chatbot, niveles de acceso, RBAC y privacidad de documentos
- [Documentación de flujo de trabajo](../../workflows/AUTHORING_GUIDE.md) — los archivos de marcado de flujo de trabajo también se sincronizan con la tienda vectorial para RAG.
- [Esquema de flujo de trabajo](../../workflows/_schema.md) — menciona la generación de incrustaciones para documentos de flujo de trabajo.
