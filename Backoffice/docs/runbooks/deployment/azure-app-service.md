# Azure App Service Deployment (Backoffice)

Practical guide for deploying and operating the Flask Backoffice on Azure App Service. See [Release process](../development/release-process.md) for the full pre/post-deploy checklist.

---

## 1. Prerequisites

| Requirement | Detail |
|-------------|--------|
| Python runtime | Must match the version in App Service configuration (check `python --version` locally vs. Azure runtime) |
| `DATABASE_URL` | **PostgreSQL is required for all environments** — development, staging, production, and testing. The application uses `JSONB`, `pgvector`, and FTS GIN indexes that are incompatible with SQLite. pgvector is also required for AI RAG — see [AI configuration](../../setup/ai-configuration.md). |
| `FLASK_APP` | Set to `run.py` (repo convention) |
| `SECRET_KEY` | Must be a long random string; stable across restarts and slots (slot-sticky setting) |
| `REDIS_URL` | Optional but recommended for multi-worker deployments (rate limiting, session sharing) |
| AI keys | `OPENAI_API_KEY`, optionally `GEMINI_API_KEY` or Azure OpenAI credentials — see [AI configuration](../../setup/ai-configuration.md) |

---

## 2. Key Application Settings (Azure App Service)

Configure these in Azure Portal → App Service → Configuration → Application settings.

### Slot-sticky settings (must NOT be swapped between slots)

Mark these as **deployment slot settings** in Azure so they stay on their respective slot during a slot swap:

- `DATABASE_URL` — each slot should point at its own DB (or staging and prod share? — align with your environment strategy)
- `SECRET_KEY` — if different per slot
- `REDIS_URL` — if slots have separate Redis instances
- Provider API keys (`OPENAI_API_KEY`, etc.) — if staging uses a different key/quota

### Non-sticky settings (swap with slot)

These carry the app's code-coupled configuration and should travel with the slot swap:
- `FLASK_APP=run.py`
- `AI_AGENT_ENABLED`
- `AI_EMBEDDING_PROVIDER`
- Feature flags and non-secret config

> Misclassifying a secret as non-sticky is a common cause of production incidents after slot swaps — double-check after every swap.

---

## 3. Startup Command

Azure App Service needs to know how to start the Flask app. Ensure the startup command (or `web.config` / Procfile) is configured to run:

```bash
gunicorn --config=config/gunicorn.conf.py run:app
```

Or inline (override specific settings via env vars listed in §3a):
```bash
gunicorn --bind=0.0.0.0:8000 --workers=4 --worker-class=gthread --threads=4 --timeout=120 run:app
```

> WebSocket (`/api/ai/v2/ws`) requires a worker class that supports long-lived connections (`gthread` supports this). If an Application Gateway is in front, set its backend timeout ≥ 300s to accommodate AI SSE streams.

### 3a. Recommended Application Settings (avoid 502/504)

Set these in Azure Portal → App Service → Configuration → Application settings:

| Setting | Recommended value | Why |
|---------|------------------|-----|
| `GUNICORN_TIMEOUT` | `60` (config default) | Under the `gthread` worker class this is a **dead-worker detector, not a request timeout** — the main loop heartbeats while requests run on pool threads, so a stuck request never trips it (App Gateway 504s the client at ~30s regardless). It must comfortably exceed worst-case recycle teardown: `GUNICORN_GRACEFUL_TIMEOUT` (15s) + scheduler shutdown wait (10s). The former 25s default made recycles a coin-flip and caused the 2026-07-16 `WORKER TIMEOUT` bursts; values like 120 just delay dead-worker replacement |
| `GUNICORN_WORKERS` | `3` or `4` (explicit) | Prevents auto-detection from over-provisioning workers that exhaust RAM; scale App Service plan instead |
| `GUNICORN_THREADS` | `8` (config default) | Concurrent request slots per worker (I/O-bound app). Also drives the per-worker WebSocket budget (`threads − WS_RESERVED_HTTP_THREADS`); the gunicorn config writes the effective value back into the env so `ws_manager` sees it |
| `GUNICORN_KEEPALIVE` | `75` (config default) | Backend keepalive should outlive App Gateway's connection reuse so gunicorn never closes an idle connection the gateway is about to reuse (sporadic 502s). Idle sockets sit in the poller, not on threads |
| `GUNICORN_MAX_REQUESTS` | `500` | Workers recycle more often but with smaller per-worker memory footprint; jitter spreads restarts |
| `GUNICORN_MAX_REQUESTS_JITTER` | `100` | Prevents all workers from recycling simultaneously |
| `SCHEDULER_LOCK_FAIL_OPEN` | unset | Scheduler-lock filesystem errors **fail closed** (worker skips starting the scheduler) because duplicate schedulers have sent duplicate digest emails before. Set `true` only as a temporary escape hatch if lock-file I/O is broken and the scheduler must run |
| `DB_STATEMENT_TIMEOUT_MS` | `120000` | Kills runaway DB queries (2 min) so pool connections aren't held indefinitely |
| `DB_CONNECT_TIMEOUT` | `10` | Aborts stalled PostgreSQL TCP handshakes (e.g. private-endpoint cold start) |
| `WEBSITES_CONTAINER_START_TIME_LIMIT` | `230` | Azure waits up to this many seconds for the container to pass the startup/warmup probe. Entrypoint (translations + migrations + tour JSON + Gunicorn) needs **~45s** before `/health` returns 200; without this setting prod saw `ContainerStartupFailure` ~7s after a health-check config change (2026-07-30). Use `230` (platform default ceiling) or higher if startup still races |
| `WEBSITE_HEALTHCHECK_PATH` | `/health` | App Service health probe path (Monitoring → Health check). Lightweight route in `app/routes/public.py` — no DB check by default (`HEALTH_CHECK_DB=false`). Do **not** enable until `WEBSITES_CONTAINER_START_TIME_LIMIT` comfortably exceeds cold-start duration |
| `WEBSITE_HEALTHCHECK_MAXPINGFAILURES` | `10` | Consecutive probe failures before Azure replaces the instance |
| `REDIS_URL` | `rediss://<host>:6380/0` | Cross-worker coordination (not sessions). **SKU:** [Azure Managed Redis Balanced B0 — West Europe](redis-provisioning.md). |

> **Redis SKU:** [Redis provisioning](redis-provisioning.md) — **Azure Managed Redis Balanced B0** (~CHF 11/mo staging single-node, ~CHF 22/mo prod two-node HA in West Europe).
| `SCHEDULER_DISABLE_ALL_WORKERS` | `true` (if using Azure Function/Container Jobs for background tasks) | Prevents N schedulers running the same DB jobs N times in parallel |

> **Without `REDIS_URL`**: enable **ARR Affinity** (Azure Portal → App Service → Configuration → General settings → ARR Affinity = **On**) so Flask sessions are reliably routed to the same worker.

> **With `REDIS_URL`**: ARR Affinity can be **Off**, which improves load distribution.

> **Scaling to ≥2 instances without Redis:** see [Multi-instance without Redis](multi-instance-without-redis.md) for the risk register (duplicate schedulers, rate limits, presence) and mitigations.

### 3b. Azure Application Gateway / Front Door timeout

If traffic passes through Application Gateway or Front Door before reaching App Service, set the **backend HTTP settings request timeout** ≥ 300s for AI chat/agent endpoints. The App Service front-end timeout (≈230s) still applies for requests that bypass the gateway.

### 3c. P&B Progress report generation

The P&B Progress tab generates multilingual HTML, PDF, Word, and figure packages via a background build (Quarto + Playwright). **No extra App Service settings are required** — defaults are baked into [`entrypoint.sh`](../../../entrypoint.sh) and [`plugins/pb_progress/service.py`](../../../plugins/pb_progress/service.py):

- On Linux container start, `entrypoint.sh` ensures Playwright Chromium under `/home/site/playwright-browsers` and Quarto 1.6.42 under `/home/site/quarto` when missing (both persist on the worker volume across container recycles).
- On Azure (`azure_blob` storage), the build uses `PB_BUILD_WORKERS=1` (sequential per-language Chromium) and runs Word before PDF to stay within App Service memory limits. Local dev uses `PB_BUILD_WORKERS=2` with parallel Word/PDF when appropriate.
- Build subprocess uses report year `2026` and blob-persisted outputs under `pb_progress/`.

Report generation is CPU- and memory-intensive; expect **5–15 minutes** per full build on P1v3. The `/generate` endpoint returns immediately after starting a background thread. Build status and outputs persist to blob storage (`pb_progress/status.json`, `pb_progress/output/*`) and survive container restarts.

---

## 4. Deploy Sequence

For every deployment that may include schema changes:

```
1. Confirm single migration head:
   python -m flask db heads        → must be ONE head

2. Deploy code to staging slot (not production yet)

3. On staging slot, apply migrations:
   python -m flask db upgrade

4. Run staging smoke tests (see §6)

5. Swap staging → production:
   az webapp deployment slot swap \
     --name <webapp-name> \
     --resource-group <rg-name> \
     --slot staging \
     --target-slot production

6. Verify production (see §6)

7. Monitor logs for 10+ minutes:
   az webapp log tail --name <webapp-name> --resource-group <rg-name>
```

**If the deployment includes only code changes (no migrations):** Steps 1 and 3 can be skipped, but it is still good practice to confirm `db heads`.

---

## 5. Streaming Logs

Requires Azure CLI authentication (`az login`) and appropriate subscription permissions.

```bash
# Stream live stdout/stderr
az webapp log tail --name <webapp-name> --resource-group <resource-group-name>

# Filter to application logs only (exclude IIS/platform)
az webapp log tail --name <webapp-name> --resource-group <rg-name> --provider application

# Download log archive for a time window
az webapp log download --name <webapp-name> --resource-group <rg-name> --log-file incident-logs.zip
```

---

## 6. Smoke Test Checklist

Run after every deployment to staging and production:

```
[ ] Anonymous: root URL / health landing → HTTP 200
[ ] Authenticated: login as System Manager → admin dashboard loads
[ ] Form: load an entry form for a known assignment → no JS errors
[ ] Admin: load Assignment Management page → list loads
[ ] AI health: GET /api/ai/v2/health → { "status": "ok" }
[ ] Migration: python -m flask db current → matches expected revision
[ ] Logs: no ERROR or CRITICAL in first 2 minutes of startup
```

---

## 7. Deployment Slots (Staging / Production)

### Slot strategy

| Slot | Purpose |
|------|---------|
| `production` | Live environment — users access this |
| `staging` | Pre-swap validation — matches production infrastructure |

**Always deploy to staging first, verify, then swap.** Never deploy directly to production unless it is an emergency hotfix with confirmed minimal risk.

### After a swap

1. Check **sticky settings** (`DATABASE_URL`, `SECRET_KEY`, provider keys) are correct for production — verify in Azure Portal.
2. Run the smoke test checklist.
3. Keep the previous production slot warm for at least 30 minutes in case a rollback swap is needed.

### Rollback

```bash
az webapp deployment slot swap \
  --name <webapp-name> --resource-group <rg-name> \
  --slot production --target-slot staging
```

This swaps back to the previous code. **Note:** If migrations ran against the production DB, a slot swap does not revert the schema — the previous code must be forward-compatible with the applied migrations, or you restore from a DB snapshot.

---

## 8. Multi-Worker Considerations

| Feature | Without Redis | With Redis |
|---------|--------------|-----------|
| Session sharing | Requires ARR Affinity (sticky sessions) | Shared across workers — no affinity needed |
| Rate limiting (authenticated APIs / AI) | Per-process (inconsistent) | Cross-worker (consistent) |
| AI WebSocket (`/api/ai/v2/ws`) | Requires affinity or single worker | Requires affinity or single worker |
| Presence heartbeats | In-memory (per-worker, clears on restart) | Redis-backed (shared, survives restart) |

**Recommendation:** Configure `REDIS_URL` for any deployment with 2+ workers. Provision **[Azure Managed Redis Balanced B0 — West Europe](redis-provisioning.md)** (Private Link; ~CHF 22/mo two-node HA).

**ARR Affinity:** Enable in Azure Portal → App Service → Configuration → General settings → ARR Affinity = On. Required when Redis is not configured.

---

## 9. PostgreSQL restore (Flexible Server and private endpoints)

If production uses **Azure Database for PostgreSQL Flexible Server** with **private networking only** (no public access):

- Restoring from backup typically provisions a **new** Flexible Server — hostname and connection targets change.
- **Private endpoints are not carried over** to the new server; the **infrastructure team must recreate them** (and Private DNS / VNet linkage as per your standard) before App Service can connect again.
- After infra validates connectivity, update **`DATABASE_URL`** (and any Key Vault references) to point at the restored instance, then run post-restore checks.

Full sequence, RTO guidance, and verification checklist: **[Backup & restore](../data/backup-and-restore.md)** (§2 — Azure Flexible Server restore and private networking; §6 — post-restore verification).

---

## 10. Rollback Playbook

| Scenario | Action |
|----------|--------|
| Bad code, no migration | Slot swap back (§7) |
| Bad code, migration already applied | Restore DB from snapshot; slot swap back |
| Bad config change | Revert the changed setting in App Service configuration |
| Bad migration only (code OK) | Restore DB from snapshot; re-deploy old migration set |

> **Never run `flask db downgrade` in production** without a written recovery plan and a confirmed DB snapshot. Prefer forward-fix migrations or snapshot restore.

---

## 11. Related Runbooks

- [Release process](../development/release-process.md) — branch, pre-release, post-deploy checklist
- [Flask-Migrate & pgvector](../data/flask-migrate-and-pgvector.md) — migration safety
- [Logging & health](../observability/logging-and-health.md) — reading logs, health endpoints
- [Security setup](../../setup/security.md) — secrets, CORS, rate limiting
- [AI configuration](../../setup/ai-configuration.md) — provider keys, model settings
