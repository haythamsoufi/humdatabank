# AI System Full Upgrade Plan – Status

Phases 1–4 and 5A–5B are complete. Remaining: 5C, 5D, 5E.

## Phase 5: Maintainability & Observability

| Item | Description | Status |
|------|-------------|--------|
| **5A** | Split `ai_tools_registry.py` and `ai_agent_executor.py` into sub-packages | ✅ Done |
| **5B** | Abstract LLM and embedding providers behind interfaces | ✅ Done |
| **5C** | Externalize model pricing to config/DB | ✅ Done |
| **5D** | Optional OpenTelemetry tracing | ✅ Done |
| **5E** | Unit/integration tests for core AI services | ✅ Done |

### 5B (Done)
- **`app/services/ai_providers/`**: `EmbeddingProvider`, `ChatCompletionProvider`; `OpenAIEmbeddingProvider`, `LocalEmbeddingProvider`, `OpenAIChatCompletionProvider`; `get_embedding_provider()`.
- **`AIEmbeddingService`** uses provider from config; supports `AI_EMBEDDING_PROVIDER=openai|local`.

### 5C (Done)
- **`app/utils/ai_pricing.py`**: Central defaults for chat and embedding (per 1M tokens); `get_chat_pricing()`, `get_embedding_pricing()`, `estimate_chat_cost()`.
- **Config**: Optional `AI_MODEL_PRICING` (JSON) overrides: `{"chat": {"model": {"input": 0.25, "output": 2.0}}, "embedding": {"model": 0.02}}`.
- **Wired**: `ai_runtime_utils.estimate_openai_cost`, `AIEmbeddingService.estimate_cost`, `OpenAIEmbeddingProvider` cost, `routes/ai.py` telemetry cost, `chatbot_telemetry.estimate_cost`.

### 5D (Done)
- **`app/utils/ai_tracing.py`**: Optional OpenTelemetry spans; `span(name, attributes)` context manager, `add_event()`. No-op when `AI_OPENTELEMETRY_ENABLED` is False or opentelemetry not installed.
- **Config**: `AI_OPENTELEMETRY_ENABLED` (default False), `OTEL_SERVICE_NAME`.
- **Integration**: `AIEmbeddingService.generate_embedding()` wrapped in `ai.embedding.generate` span. Other call sites (agent execute, chat route) can use `from app.utils.ai_tracing import span` the same way.

### 5E (Done)
- **tests/unit/test_utils/test_ai_pricing.py**: `get_chat_pricing`, `get_embedding_pricing`, `estimate_chat_cost`, config override.
- **tests/unit/test_utils/test_ai_tracing.py**: `span()` no-op when disabled or no app context, `add_event()` no-op.
- **tests/unit/test_services/test_ai_providers.py**: `LocalEmbeddingProvider` (generate, batch, empty text), `get_embedding_provider()` (local config, openai requires key).
- **tests/unit/test_services/test_ai_services.py**: fixture updated to patch `app.services.ai_tools.registry.AIVectorStore` (implementation in package).
