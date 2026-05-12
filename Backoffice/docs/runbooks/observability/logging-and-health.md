# Logging, Health Checks, and Telemetry

Where to look when the app misbehaves in production, how to interpret what you find, and which endpoints expose subsystem health.

---

## 1. Application Logs (Azure App Service)

### Stream live logs

```bash
az webapp log tail --name <webapp-name> --resource-group <resource-group-name>
```

Requires `az login` and appropriate subscription permissions. Use `--provider application` to filter to app stdout/stderr only (excludes IIS/platform logs).

**Download a historical slice** (when you need to search an incident window offline):
```bash
az webapp log download --name <webapp-name> --resource-group <rg-name> --log-file logs.zip
```

### Log levels

| Level | Meaning | Action |
|-------|---------|--------|
| `DEBUG` | Verbose trace — usually silenced in production | None unless debugging |
| `INFO` | Normal operational messages | Review periodically |
| `WARNING` | Something unexpected but recoverable | Investigate if recurring |
| `ERROR` | An operation failed; user may have seen an error | Investigate promptly |
| `CRITICAL` | Application-level failure | Immediate investigation |

### Common log patterns to watch

| Log pattern | What it means |
|------------|--------------|
| `WARNING ... unguarded admin route` | A new `/admin` route was deployed without an RBAC guard. Treat as a security finding — add `@admin_required` or `@permission_required`. |
| `ERROR ... OperationalError` | Database connection or query failure. Check DB connectivity and connection pool saturation. |
| `ERROR ... MigrationError` or `alembic.exc` | A migration failed mid-apply. DB may be in inconsistent state — escalate immediately. |
| `WARNING ... multiple heads` | Migration graph has branched — `flask db upgrade` will not run safely. |
| `ERROR ... OpenAI` / `ERROR ... provider` | AI provider is unreachable or API key is invalid. Check AI health endpoint. |
| `WARNING ... rate limit` | Rate limiter hit — authenticated JSON or admin API traffic too fast. Legitimate spike or scripted client. |
| `ERROR ... CSRF` | CSRF token mismatch. Common after session expiry or behind a misconfigured load balancer. |
| `INFO ... cleaned up N sessions` | Normal — session cleanup ran. |

### Enabling verbose form debugging

For deep investigation of form save/load issues only — **disable after investigation**:
```bash
# In App Service Application Settings (or .env locally):
VERBOSE_FORM_DEBUG=true
```

This emits detailed per-field logs. Do not leave on in production (noise, potential PII exposure).

---

## 2. Health Endpoints

### AI system health

```
GET /api/ai/v2/health
```

**Sample healthy response:**
```json
{
  "status": "ok",
  "agent_available": true,
  "providers": {
    "openai": { "available": true, "model": "gpt-4o" },
    "gemini": { "available": false }
  },
  "rag_enabled": true,
  "websocket_enabled": true
}
```

**When to check:**
- AI chat returns empty or falls back silently.
- Users report "something went wrong" in chat with no error details.
- After rotating `OPENAI_API_KEY` or changing `OPENAI_MODEL`.

**Degraded states:**
- `agent_available: false` → `AI_AGENT_ENABLED` is `false` in config, or agent initialization failed.
- Provider shows `available: false` → key missing, invalid, or provider is down.
- `rag_enabled: false` → pgvector not configured or `ai_documents` table missing.

Detailed env reference: [`../../setup/ai-configuration.md`](../../setup/ai-configuration.md).

### Application reachability

For a quick "is the app responding?" check without authentication:
```
GET /                         ← Public landing page
GET /api/ai/v2/health         ← AI health (no auth required)
```

If either returns 5xx or times out, check the Azure App Service status page and stream application logs.

---

## 3. Startup Diagnostics

Every app restart emits diagnostic output in logs. Look for:

### RBAC startup audit

On boot, unguarded `/admin` routes emit:
```
WARNING  rbac_audit: unguarded admin route: /admin/some/path [endpoint_name]
```

This is a **security signal** — every `/admin` route must have `@admin_required`, `@permission_required`, or a documented exemption (`@rbac_guard_audit_exempt`). See [`../security/rbac-admin-route-audit-exemptions.md`](../security/rbac-admin-route-audit-exemptions.md).

### Migration state

At startup the app does **not** auto-migrate. If you see schema errors (`no such column`, `undefined column`), the migration was not applied. Fix:
```bash
python -m flask db heads    # must be one head
python -m flask db upgrade  # apply pending migrations
```

### Provider key validation

If an API key is set but invalid, the AI service logs an error at first use, not at startup. Watch for `ERROR` entries from provider clients after the first AI request.

---

## 4. OpenTelemetry (Optional)

When `AI_OPENTELEMETRY_ENABLED=true` and the `opentelemetry` package is installed, AI-related code emits spans to a configured OTEL collector:

- Span name for embeddings: `ai.embedding.generate`
- Other spans can be added via `from app.utils.ai_tracing import span` in new code.
- Default is **off** (`AI_OPENTELEMETRY_ENABLED=false`). Enable only if your platform has an OTEL collector configured.
- Config: `AI_OPENTELEMETRY_ENABLED`, `OTEL_SERVICE_NAME`.

See `app/utils/ai_tracing.py` for implementation.

---

## 5. Client-Side Diagnostics

### Browser console errors

After any deployment, open the browser DevTools console on:
1. A public-facing page (e.g. landing page).
2. An admin page (e.g. form builder).
3. An entry form.

Watch for:
- **CSP violations** (`Refused to execute inline script...`) — indicates a new inline `<script>` is missing `nonce="{{ csp_nonce() }}"`.
- **JS exceptions** — likely broken by a template/script change.
- **Failed API calls** (network tab) — 401 (session expired), 403 (WAF or RBAC), 500 (server error).

### IndexedDB / Azure Front Door caching issues

If a form behaves strangely for specific users behind CDN or proxy (e.g. stale cached responses, mismatched state):

See: `Backoffice/app/static/docs/AZURE_INDEXEDDB_DEBUGGING.md`

---

## 6. Performance Signals

| Symptom | Where to look |
|---------|--------------|
| Slow page loads on admin pages | Azure App Service metrics → Response time; DB query time in logs |
| AI chat takes >30s | AI agent timeout (`AI_AGENT_TIMEOUT_SECONDS`); check `ai_reasoning_traces` for stuck runs |
| Excel export times out | Memory/compute limits; consider exporting per-country batch |
| 429 rate limit errors | Rate-limit decorators on sensitive routes; Redis consistency if multi-worker |
| Memory creep on workers | Session table growth (run `cleanup-sessions`); AI embedding cache size |

---

## 7. Key Config Variables for Observability

| Variable | Default | Effect |
|----------|---------|--------|
| `VERBOSE_FORM_DEBUG` | `false` | Enable detailed form processing logs |
| `AI_OPENTELEMETRY_ENABLED` | `false` | Emit OTEL spans for AI calls |
| `OTEL_SERVICE_NAME` | — | Service name in OTEL traces |
| `CLIENT_CONSOLE_LOGGING` | `false` | Enable `console.log` in browser (dev only) |

---

## Related Runbooks

- [General incident triage](../incidents/general-incident-triage.md) — what to do with what you find here.
- [Azure App Service](../deployment/azure-app-service.md) — streaming logs, slots, restarts.
- [AI configuration](../../setup/ai-configuration.md) — provider keys, model settings, cost limits.
