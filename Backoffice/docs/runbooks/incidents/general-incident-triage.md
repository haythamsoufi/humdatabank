# General Incident Triage (Backoffice)

Use this playbook when behaviour breaks in staging or production and the cause is not immediately obvious. Work through the layers in order — most incidents resolve at layer 1 or 2.

---

## 1. Classify Where the Failure Happens

```
User / Browser  →  CDN / WAF (Azure)  →  App (Flask workers)  →  Database  →  Integrations (OpenAI, LibreTranslate, …)
```

| Symptoms | Likely layer | Go to |
|----------|-------------|-------|
| `403 Forbidden`, `Server: Microsoft-Azure-Application-Gateway*` in response headers | Edge WAF blocking body or path | [WAF 403 guide](waf-403-form-payload-refactor-guide.md) |
| 502 / 504 at gateway, site completely unreachable | App stopped / slot misconfigured / outbound block | [Azure App Service](../deployment/azure-app-service.md), [Logging & health](../observability/logging-and-health.md) |
| 500 from Flask; `error_id` in API response | Application exception in code | Application logs — tail and grep for the `error_id` |
| `no such column`, `undefined column`, schema errors | Migration not applied or multiple heads | [Flask-Migrate runbook](../data/flask-migrate-and-pgvector.md) |
| Sessions drop; CSRF errors after deploy | `SECRET_KEY` changed or cookie domain mismatch | [Session management](../sessions/session-management.md), [Security setup](../../setup/security.md) |
| AI chat empty, "no provider configured" | Missing API keys or wrong model name | [AI configuration](../../setup/ai-configuration.md), [AI health endpoint](../observability/logging-and-health.md#2-health-endpoints) |
| Form auto-save fails silently | WAF blocking save endpoint or JS error | [WAF 403 guide](waf-403-form-payload-refactor-guide.md), browser console |
| Excel export returns error | Server timeout or memory exhaustion | Logs — check for OOM; try smaller export (per-country) |
| Translation not appearing | LibreTranslate unreachable or language disabled | [Integrations overview](../integrations/overview.md) |
| Public-facing indicators/map data stale | Public assignment not published or downstream cache lag | Admin → Public Assignments → confirm published status; allow time for caches to refresh |

---

## 2. Minimum Information to Capture

Before investigating, collect:

- **UTC time window** and timezone of reporters.
- **URL path + HTTP method** (e.g. `POST /admin/settings`).
- **HTTP status code** the user received.
- **User role** (guest / focal point / admin / system manager).
- **Browser version** (and any client-reported build identifier from support tickets).
- **Request / correlation ID** if your hosting layer injects one (check response headers).
- **Whether the same action succeeds** on another environment (staging/local) or for another user.
- **Recent changes**: last deployment date, config changes, new migrations.

---

## 3. Safe First Checks (Read-Only)

Do these before making any changes:

### 3a. Tail application logs
```bash
az webapp log tail --name <webapp-name> --resource-group <rg-name>
```
Filter the output for `ERROR`, `CRITICAL`, and the time window of the incident.

### 3b. Check AI health endpoint
```
GET https://<app-url>/api/ai/v2/health
```
If `status` is not `ok`, the AI subsystem is degraded. Check provider keys.

### 3c. Confirm migration heads
```bash
python -m flask db heads
```
Must return exactly one revision. Multiple heads = migration graph branched; do not run `db upgrade`.

### 3d. Compare recent config changes
App Service configuration changes (env vars) often explain regressions faster than reading code diffs. Check the Azure App Service "Environment variables" history or deployment log for recent changes.

### 3e. Check RBAC startup warnings
Grep the startup logs for:
```
WARNING  rbac_audit
```
A newly deployed admin route missing its guard can cause unexpected permission behaviour.

---

## 4. Scenario-Specific Playbooks

### Scenario F: Recurring 502 / 504 errors

These errors indicate the Azure front-end is not getting a response from a gunicorn worker in time. Work through each cause in order.

#### F1. Gateway timeout vs gunicorn timeout (most common 504 source)

The Application Gateway 504s clients after its **~30s backend timeout** (Azure's front-end cuts at ~230s when no AGW is in front). Gunicorn's `GUNICORN_TIMEOUT` (default **60s**) does **not** abort long requests under the `gthread` worker class — the worker's main loop keeps heartbeating while requests run on pool threads — so a slow request 504s at the gateway while the worker thread keeps running and holds its DB connection. `[STUCK_REQUEST]` log lines (warning at 15s, critical at 23s) are the visibility for this, not `WORKER TIMEOUT`.

- Don't raise `GUNICORN_TIMEOUT` to "fix" slow requests — it only delays replacement of genuinely dead workers. Fix or bound the slow endpoint instead.
- Keep `GUNICORN_TIMEOUT` (60) well above `GUNICORN_GRACEFUL_TIMEOUT` (15) + scheduler shutdown wait (10), or recycling workers get SIGKILLed mid-teardown (2026-07-16 incident).
- For AI streaming (SSE), ensure the Application Gateway backend timeout ≥ 300s, or reduce `AI_SSE_IDLE_TIMEOUT_SECONDS` ≤ 200.
- `AI_AGENT_TIMEOUT_SECONDS` should be ≤ 100 if no Application Gateway is in front.

#### F2. Worker recycling during high load (intermittent 502)

Gunicorn recycles workers after `GUNICORN_MAX_REQUESTS` requests (default 1000). If ARR Affinity (sticky sessions) routes a user to a recycling worker, they get a 502 for the ~30s restart window.

- Confirm ARR Affinity is **On** in Azure Portal → App Service → Configuration → General settings (required without Redis).
- Or configure `REDIS_URL` to eliminate the ARR Affinity dependency.
- Reduce `GUNICORN_MAX_REQUESTS` to 500 with `GUNICORN_MAX_REQUESTS_JITTER=100` to spread recycling more evenly.

#### F3. DB connection pool saturation (cascading 504s)

Symptoms: `QueuePool limit of size X overflow Y reached` in logs, then 504s on otherwise fast pages.

Root cause: scheduler jobs (email retry, notification dispatch) run in **every** gunicorn worker simultaneously (fixed in `app/scheduler.py` — only one worker now runs the scheduler via `_is_scheduler_worker()`). Also common during post-deploy startup when deferred tasks and RBAC seed compete for connections.

- Check `SQLALCHEMY_POOL_SIZE` × workers does not exceed PostgreSQL `max_connections` tier limit (B1ms = 50, B2s = 100, GP-2vCore = 200).
- Verify `DB_STATEMENT_TIMEOUT_MS=120000` is set (added to `ProductionConfig`) so runaway queries release their connections.
- Set `DB_CONNECT_TIMEOUT=10` to abort stale TCP handshakes (also added to `ProductionConfig`).
- Stream logs and grep for `QueuePool`:
  ```bash
  az webapp log tail --name <app> --resource-group <rg> | grep -i "queuepool\|pool\|timeout"
  ```

#### F4. Worker OOM crash → 502 while new worker starts

Large AI agent runs, Excel exports, or form renders can exhaust worker memory. The OS kills the worker and gunicorn starts a new one — during which all requests sticky-routed to that worker get 502.

- Check App Service metrics: **Memory Working Set** → spikes before 502 bursts.
- Scale up the App Service plan (P2v3 = 8 GB vs P1v3 = 3.5 GB).
- Set `GUNICORN_WORKERS` explicitly (e.g., `3`) rather than letting gunicorn auto-detect `(2×CPU+1)` on a CPU-rich SKU with limited RAM.

#### F5. SCHEDULER_DISABLE_ALL_WORKERS for external job runner

If background jobs are managed by an Azure Container Job or Function:
```
SCHEDULER_DISABLE_ALL_WORKERS=true
```
This prevents all gunicorn workers from starting APScheduler, eliminating scheduler-related DB pressure entirely.

#### F6. Verify the health endpoint is configured as the App Service health probe

See also the dedicated report [Gateway 504 / worker saturation](gateway-504-worker-saturation.md) for recurring presence/notification 504 patterns, evidence from production, and a layered mitigation plan.

In Azure Portal → App Service → Monitoring → **Health check**: set path to `/health`. Azure will automatically restart unhealthy instances and stop routing to them — dramatically reducing how long a 502 window lasts.

---

### Scenario A: All users cannot log in

1. Confirm the app is running: `GET /` — if 502, the app is down.
2. Check startup logs for Python exceptions during app initialization.
3. If `SECRET_KEY` was recently rotated: all existing sessions are invalid — expected. Users must log in again.
4. If `DATABASE_URL` was changed: app may be pointing at empty/wrong DB.

### Scenario B: A specific user cannot access a page

1. Check the user's role and country assignments (Admin → User Management).
2. Check logs for `403` or RBAC-related messages for that user's requests.
3. Confirm the route has the correct RBAC guard (not a new route lacking `@admin_required`).
4. If the user is a focal point: confirm the assignment for their country is open.

### Scenario C: Form submissions failing

1. Open browser DevTools → Network tab → reproduce the save action → inspect the failing request.
2. If `403` from the server with `Microsoft-Azure-Application-Gateway` in headers: WAF block — see [WAF 403 guide](waf-403-form-payload-refactor-guide.md).
3. If `500`: tail application logs for the corresponding `ERROR` traceback.
4. If `CSRF` error: session expired mid-form (user left browser open too long). User must refresh and re-enter.
5. If no network request at all: JS error — check browser console.

### Scenario D: AI chat not working

1. `GET /api/ai/v2/health` → check which provider is unavailable.
2. If provider unavailable: verify API key in App Service env vars; test the key directly with provider's API.
3. If `agent_available: false`: check `AI_AGENT_ENABLED=true` in config.
4. If chat works but responses are poor: see [RAG quality](../ai/rag-quality-and-embeddings.md).
5. If costs are spiking: see [Chat cost drivers](../ai/ai-chat-cost-drivers.md).

### Scenario E: Database/migration issues

1. `python -m flask db heads` → if not one head, **stop all migration activity**.
2. `python -m flask db current` → confirm which revision is applied.
3. If schema errors appear: the migration was not run after deployment. Run `python -m flask db upgrade` (confirm single head first).
4. If a migration failed mid-apply: restore from the pre-deploy snapshot — do not attempt `db downgrade` without a recovery plan.

---

## 5. Escalation

### Infrastructure / WAF / firewall
Include in escalation ticket:
- WAF rule ID (`ruleId` from WAF logs)
- Matched field name (`matchVariableName`)
- Full URI and HTTP method
- Time window (UTC)
- Business justification for the content being legitimate

Request: **targeted path + argument exclusion only** — not global rule disablement.

### Security / RBAC regression
Never remove guards without reviewing [RBAC audit exemptions policy](../security/rbac-admin-route-audit-exemptions.md) and getting a second reviewer.

### Database corruption / migration failure
1. Immediately take a snapshot of the current DB state.
2. Do not run further migrations or schema-touching code.
3. Engage the development team with: current revision (`flask db current`), heads output, and the migration error message.
4. **If recovery involves restoring Azure PostgreSQL Flexible Server from backup:** restoring usually creates a **new** server behind **private networking** — engage **infrastructure** early to **recreate private endpoints and DNS**; then update `DATABASE_URL`. See [Backup & restore](../data/backup-and-restore.md) §2.

---

## 6. Post-Incident

After resolving a production incident:

1. Confirm the fix is stable (monitor logs for 30+ minutes).
2. Write a brief incident summary: what broke, why, how it was fixed, how to prevent recurrence.
3. If a WAF exclusion was added: update the [WAF 403 guide](waf-403-form-payload-refactor-guide.md) with the specific rule/field/endpoint.
4. If a RBAC gap was found: update [RBAC audit exemptions](../security/rbac-admin-route-audit-exemptions.md).
5. Update this runbook if you discovered a scenario that should be captured here.
