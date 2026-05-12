# Integrations overview (translations, storage, external AI)

Thin index for optional services the Backoffice plugs into — full env keys stay in **`env.example`** / config.

| Integration | Operational doc |
|-------------|----------------|
| LibreTranslate (optional machine translation) | [`../../setup/libretranslate.md`](../../setup/libretranslate.md) |
| Azure file mounts / uploads | [`../../setup/azure-storage.md`](../../setup/azure-storage.md), [`../../setup/persistent-translations.md`](../../setup/persistent-translations.md) |
| AI providers (OpenAI, Gemini, Azure OpenAI), embeddings, RAG | [`../../setup/ai-configuration.md`](../../setup/ai-configuration.md) |
| Security (CORS, rate limits, API keys rotation) | [`../../setup/security.md`](../../setup/security.md) |

**Failure modes:**

- LibreTranslate unreachable → translations fall back/disabled paths depending on toggles — check service health and outbound firewall.
- Azure mount missing → uploads or translation persistence quietly fail paths depending on caller — correlate with `/admin` document upload logs.
- AI provider outage → **`/api/ai/v2/health`** degraded; chat may fallback — observability [`../observability/logging-and-health.md`](../observability/logging-and-health.md).
