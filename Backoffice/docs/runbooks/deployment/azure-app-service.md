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
gunicorn --bind=0.0.0.0:8000 --workers=4 run:app
```

Or for single-worker with WebSocket support (`flask-sock`):
```bash
gunicorn --bind=0.0.0.0:8000 --worker-class=geventwebsocket.gunicorn.workers.GeventWebSocketWorker --workers=1 run:app
```

> WebSocket (`/api/ai/v2/ws`) requires a worker class that supports long-lived connections. If WebSocket is not needed, standard sync workers are fine and allow scale-out.

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

**Recommendation:** Configure `REDIS_URL` in production for any deployment with 2+ workers.

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
