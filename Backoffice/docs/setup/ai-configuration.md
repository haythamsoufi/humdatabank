# AI chat and RAG configuration

The Backoffice includes an AI chat and RAG (document QA) stack. For the full reference (endpoints, env vars, troubleshooting), see **CLAUDE.md** at the project root.

## Required for AI chat (non-fallback)

- At least one of: `OPENAI_API_KEY`, `GEMINI_API_KEY`, or Azure/Copilot keys (`AZURE_OPENAI_KEY` + `AZURE_OPENAI_ENDPOINT`, or `COPILOT_API_KEY`).
- `SECRET_KEY` is required for AI token signing (Bearer tokens for Website/Mobile).

## Optional

- **WebSockets** (streaming chat, document QA WS): install `flask-sock`. Without it, HTTP and SSE chat still work.
- **Cross-worker rate limiting:** set `REDIS_URL` so WebSocket rate limits apply across workers; otherwise in-memory (per-worker) limits are used.
- **RAG (document search):** run migrations so `ai_documents`, `ai_embeddings`, `ai_document_chunks` exist. For embeddings use `OPENAI_API_KEY` when `AI_EMBEDDING_PROVIDER=openai`, or a local model when `AI_EMBEDDING_PROVIDER=local` (set `AI_EMBEDDING_DIMENSIONS` to match the DB column).

## Health check

- `GET /api/ai/v2/health` — returns config checks and `agent_available`.
- `GET /api/ai/v2/health?probe=embedding` — also runs a minimal embedding call (slower).

## AI-related migrations

After pulling changes that add or modify AI tables (e.g. `total_embeddings` on `ai_documents`):

```bash
python -m flask db upgrade
```

## User-facing and admin docs

- [AI Document Library and embeddings](../user-guides/admin/ai-document-library-and-embeddings.md)
- [AI system: security and privacy](../user-guides/admin/ai-system-security-and-privacy.md)
- [AI Use Policy](../user-guides/common/ai-use-policy.md)
