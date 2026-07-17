# Gateway 504 / Worker Saturation — Incident Report & Mitigation Plan

**Status:** Active pattern (recurring)  
**Affected environment:** Production (`ifrc-databank-app`, West Europe)  
**Primary symptom:** HTTP **504 Gateway Timeout** reported by users; often on lightweight endpoints (presence sync, notifications, profile lookups)  
**Last reviewed:** 2026-07-09

Related playbooks: [General incident triage](general-incident-triage.md) (Scenario F), [Azure App Service](../deployment/azure-app-service.md) §3a.

---

## 1. Executive summary

Production has experienced recurring **platform-level 504 errors** — timeouts returned by Azure’s edge/gateway layer before the Flask application responds. These are **not** application bugs in the URL that appears in the error (e.g. presence `/sync`). They are **collateral damage** from worker saturation: Gunicorn workers blocked on other requests, thread pool exhaustion, or worker recycle/timeout cycles.

Evidence from **2026-06-30** and **2026-07-09** shows:

- `WORKER TIMEOUT (pid:…): silent for >25s` in container logs
- App Service **Http5xx = 0** while clients see **504** (gateway-generated, not Flask 5xx)
- Failed endpoints are cheap when they succeed (presence sync ~20–80 ms)
- Heavy pages (`GET /forms/assignment/*` ~3–4 s) and admin traffic coincide with incidents
- New **platform-error diagnostics** attach worker pressure to security events but are **per-worker** — the reporting worker is often idle while another worker is stuck

**Goal of this document:** explain the failure mode and propose mitigations at **edge, platform, application, client, and observability** layers.

---

## 2. Architecture and failure path

```text
Browser  →  Application Gateway / Azure front-end  →  Gunicorn (N workers × M threads)  →  PostgreSQL
                    │                                        │
                    │  ~30 s backend timeout (AGW)           │  GUNICORN_TIMEOUT=60 s (heartbeat, not request timeout)
                    │  ~230 s App Service limit (bypass AGW) │  max_requests recycle
                    └─ Returns 504 if no response in time ───┘
```

When a worker is blocked on a long or hung request:

1. Other requests **queue** for a free thread (or wait for DB pool connections).
2. After **~25–30 seconds**, the gateway closes the connection → user sees **504**.
3. The blocked request often **never completes**, so it **does not appear** in Gunicorn access logs.
4. Gunicorn may kill the worker (`WORKER TIMEOUT`) and boot a replacement — during which more requests fail.

Presence sync, notification preferences, and profile-summary calls are **high-frequency, low-cost** polls. They fail first when capacity is exhausted, which makes them look like the cause when they are only the **canary**.

---

## 3. Incident chronology

### 3.1 2026-06-30 (Carlota TARAZONA — assignment 1641)

| Time (UTC) | Event |
|------------|--------|
| ~07:54–08:07 | ~4 min log gap — workers stuck |
| 08:09–08:11 | User login; `GET /forms/assignment/1641` **~3.77 s**; presence sync OK (20 ms) |
| 08:12:53 | **504** on `POST /api/forms/presence/assignment/1641/sync` (client reporter) |
| 08:23–08:31 | `WORKER TIMEOUT` (pid 3252); presence syncs succeeding but **~70–80 ms** (queue wait) |
| 08:31, 08:50, 08:56 | Additional worker timeouts |

**Metrics:** Requests 21 → **80/min** at 08:12; avg latency **~3 s** at 08:13; memory rising.

### 3.2 2026-07-09 (multiple users)

| Time (UTC) | Event |
|------------|--------|
| 07:16:32 | `WORKER TIMEOUT` pid **47** |
| 08:05:34 | `GET /forms/assignment/1671` **~3.9 s** + EmOps live fetch + matrix burst |
| 08:06:41 | `WORKER TIMEOUT` pid **45** → new worker pid **1943** |
| 08:12:39 | **504** presence assignment **3657** |
| 08:22–08:27 | **504** cluster: `/notifications/api`, `/notifications/api/preferences`, Carlota `/api/users/profile-summary` |
| 08:36:10 | Worker recycle → pid **2418** |
| 08:36:39 | **504** presence assignment **1673** (reporter on fresh worker, 0 in-flight) |

**Metrics:** Spike **99 req/min** at 08:06; avg latency **6–20 s** 08:15–08:30; **Http5xx = 0**; memory **1.13 → 1.32 GB**.

### 3.3 Security-event diagnostics (2026-07-09)

Platform-error payloads showed `likely_causes: ["upstream_gateway_timeout"]` with **0 stale in-flight** on the reporting worker. That is **consistent** with the failure mode, not a false negative: the stuck work was on **other workers** or had already been killed before the report was processed.

One event (08:27:01) showed **DB pool 5/5 checked out** on pid 1023 — pool pressure contributing to waits even without stale flags on the reporter.

---

## 4. Root causes (ranked)

| # | Cause | Evidence |
|---|--------|----------|
| 1 | **Worker blocked on hung/slow request** (>25 s silent) | `WORKER TIMEOUT`, log gaps, recycle + SIGKILL |
| 2 | **Thread pool saturation** | Many concurrent admin/form/API requests; cheap endpoints wait 70 ms+ then 504 |
| 3 | **Heavy server-rendered pages** | `/forms/assignment/*` 3–4 s; `/` 0.6–1.4 s; `/help/docs/*` 0.3–0.5 s each |
| 4 | **Worker recycle during load** | `Autorestarting worker after current request` + `GUNICORN_MAX_REQUESTS` |
| 5 | **DB pool pressure** (contributing) | Diagnostics: 5/5 checked out; missing explicit `DB_*` timeouts in some Azure settings |
| 6 | **Gateway timeout (30 s AGW)** | 504 without Flask `X-App-Origin`; Http5xx=0 on App Service |

**Not root cause:** Presence sync logic, specific assignment IDs, or a single user session.

---

## 5. Layered mitigation plan

Actions are grouped by where they apply. Prioritize **P0** before the next reporting cycle peak.

### 5.1 Edge / gateway (Application Gateway / WAF)

| Priority | Action | Rationale |
|----------|--------|-----------|
| P2 | Confirm AGW **backend timeout** (currently ~**30 s** per `gunicorn.conf.py` comment) vs product needs | AI/SSE needs ≥300 s on dedicated routes; general API should stay ≤30 s |
| P2 | **Separate backend pools** or routing rules: long-running paths (`/api/ai/v2/chat/stream`, exports) vs default | Prevents one slow stream from starving form/presence traffic |
| P3 | Enable / retain **AGW access logs** with `backendResponseStatus`, `timeTaken`, `backendPoolName` | 504s often never hit App Service Http5xx metrics |

*Do not* raise AGW timeout globally to “fix” 504s — that masks stuck workers and holds DB connections longer.

### 5.2 Platform — Azure App Service

| Priority | Action | Current (prod) | Recommended |
|----------|--------|----------------|-------------|
| **P0** | Verify **application console logs** level = Information | Already on File System; confirm level is not Error-only | Needed to retain `[STUCK_REQUEST]` / `WORKER TIMEOUT` in `/home/LogFiles` |
| **P0** | Set **`DB_STATEMENT_TIMEOUT_MS=120000`** | Not in app settings | Explicit in Azure config |
| **P0** | Set **`DB_CONNECT_TIMEOUT=10`** | Not in app settings | Explicit in Azure config |
| P1 | **`GUNICORN_WORKERS=3`** | **5** | **3** (handbook default; reduces RAM + pool fan-out) |
| P1 | **`GUNICORN_MAX_REQUESTS=500`**, **`GUNICORN_MAX_REQUESTS_JITTER=100`** | Default 500 in code | Confirm in Azure; avoid recycle storms |
| P1 | **`REDIS_URL`** | Not set | Sessions + rate limits across workers; allows ARR Affinity off |
| P1 | Scale **horizontally** (instance count) before adding workers | Single instance | More instances × fewer workers = better isolation |
| P2 | Scale **up** plan if memory Working Set routinely **>1.2 GB** | P1v3 ~3.5 GB | P2v3 or reduce workers |
| P2 | **`SCHEDULER_DISABLE_ALL_WORKERS=true`** if jobs run in Container Job/Function | Scheduler in one worker | Removes background DB contention from web workers |

**Pool budget:** With 5 workers × (pool 5 + overflow 10) = up to **75** connections — verify against PostgreSQL tier `max_connections`.

### 5.3 Application — Backoffice code & configuration

| Priority | Action | Detail |
|----------|--------|--------|
| **Done** (2026-07-15) | **Workflow tour endpoint**: stop eager/uncacheable fetch on every chatbot init | Tours now load lazily on chat-open, cached in `localStorage` + pre-generated static/CDN files (`flask workflows generate-static`); `Cache-Control` added to all `/api/ai/documents/workflows/*` GET routes |
| **Done** (2026-07-15) | **Notification preferences** (`/notifications/api/preferences`) fetched on *every* page load | Client now caches in `localStorage` with a 15-min TTL (`components.js`); server logs `[NOTIF_PREFS_FETCH]` to confirm hit-rate drop |
| **Done** (2026-07-15) | **WS status check** (`/notifications/api/stream/status`) fetched on *every* page load | Client caches result for 5 min; server logs `[WS_STATUS_FETCH]` |
| **Done** (2026-07-15) | **WebSocket connections consuming Gunicorn threads unbounded** — each notification/AI-chat WS holds one `gthread` worker thread for its lifetime; no shared cap existed for AI chat/doc WS | `ws_manager` now derives `max_total_connections` from `GUNICORN_THREADS - WS_RESERVED_HTTP_THREADS` (default reserve 2) and is shared across notifications + AI chat + AI docs channels; over-budget connections are rejected and the client falls back to polling/SSE (already implemented). `[WS_POOL]` INFO logs on every connect/disconnect/rejection; snapshot exposed in platform 5xx diagnostics (`worker_metrics.ws_pool`) |
| **Done** (2026-07-17) | **Recycles of workers holding live WebSockets ended in `WORKER TIMEOUT` + SIGKILL** — gthread pool threads are non-daemon (Python 3.9+), so a thread pinned by a live WS blocks `threading._shutdown()` after the worker's graceful drain; the worker goes silent until the master kills it (~25–60 s zombie per recycle, benign but noisy) | `worker_exit` hook now calls `scheduler_lock.hard_exit_if_lingering_threads`: after full teardown, if non-daemon threads survive a 1 s grace join, the worker logs them and `os._exit(0)`s instead of hanging in interpreter finalization. `worker_abort` does the same with exit code 1 (no grace), removing the `Exception ignored in threading._shutdown` traceback + double-SIGKILL noise |
| **Done** (2026-07-17) | **Presence `/sync` DB cost per tick** — every 30 s poll ran an `AssignmentEntityStatus` + entity-access query | `check_aes_access_light` now caches positive results per (user, aes) for 5 min (`data_retrieval_service.py`); steady-state presence ticks skip the DB entirely. Denials are never cached; data-bearing endpoints still re-check via `ensure_aes_access` |
| **Done** (2026-07-17) | **Presence store is per-worker memory** — with `GUNICORN_WORKERS` > 1 co-editors are only mutually visible when their requests land on the same worker (~(1/N) per record), so the presence bar/warning flickers during genuine co-editing | `presence_store.py` now uses Redis (one ZSET per assignment, self-expiring) whenever `REDIS_URL` is set — shared across workers and instances — with the previous in-memory dict as automatic fallback. No config change needed beyond deploying `REDIS_URL` (already planned in Phase 3) |
| **P1** | **Profile `/forms/assignment/<id>`** render path | 3–4 s server time; target caching, slimmer queries, deferred fragments |
| P1 | **EmOps plugin**: avoid **live GO API fetch** on form load when cache cold | 2026-07-09: `[EmOps List] No file cache; fetching live` during assignment load |
| P1 | **Matrix auto-load**: batch or lazy-load | Six parallel `POST /api/v1/matrix/auto-load-entities` on every form open |
| P2 | **Homepage / admin pages** (`GET /`, `/admin/users`) | 0.5–0.6 s; reduce template work where possible |
| P2 | **Help docs** (`/help/docs/*`) | Served by app; consider static CDN-only for docs HTML |
| P2 | Ensure **`SLOW_REQUEST_LOG_ENABLED=true`** in production and that stuck-warning thresholds fire before the AGW 30 s cut-off | Default `SLOW_REQUEST_STUCK_WARNING_SECONDS=15`, `SLOW_REQUEST_STUCK_CRITICAL_SECONDS=23` — both before the gateway 504s the client at ~30 s. Note `GUNICORN_TIMEOUT` (60 s) is a *heartbeat* check under gthread and never fires for stuck requests; `[STUCK_REQUEST]` lines are the only visibility |
| P3 | **Externalize scheduler** (email, cleanup, notifications) | Azure Container Job / Function — web workers serve HTTP only |

Presence `/sync` request volume and per-tick cost were reduced on 2026-07-17 (see rows above); the endpoint remains a canary, not a cause.

### 5.4 Client / UX (browser)

| Priority | Action | Detail |
|----------|--------|--------|
| P3 | Presence module already **backs off** and hides bar after 3 failures | Document for support; no user action required |
| P3 | Avoid treating presence 504 as form save failure | Already separate code path |
| **Done** (2026-07-17) | Reduce presence poll volume client-side | `presence.js` now (1) polls every **60 s** when no co-editors are present (30 s only during genuine co-editing), (2) elects one **leader tab per assignment** via `BroadcastChannel` so extra tabs render broadcast results instead of polling, and (3) remembers dismissed warnings for 10 min so brief server-side presence flickers no longer re-trigger the concurrent-edit warning/auto-expand |

### 5.5 Observability & alerting

| Priority | Action | Detail |
|----------|--------|--------|
| Done | **Platform-error diagnostics** on 502/503/504 security events | `diagnostics_summary`, `worker_metrics`, `likely_causes` |
| Done (2026-07-15) | **WS thread-pressure visibility**: `worker_metrics.ws_pool` (`active_total`, `pct_of_budget_used`, `by_channel`) | New `ws_thread_pressure` cause fires when a worker's WS connections use ≥75% of its thread budget. Grep prod logs for `[WS_POOL]` (connect/disconnect/rejected), `[NOTIF_PREFS_FETCH]`, `[WS_STATUS_FETCH]`, `[WORKFLOW_TOUR_DYNAMIC_HIT]` (all INFO level) to confirm the fetch-reduction and thread-budget fixes are holding in production |
| **P1** | **Cross-worker snapshot** (Redis ring buffer of last N stuck requests + last `WORKER TIMEOUT` per process) | Fixes “0 in-flight on reporter” blind spot |
| **P1** | Log Analytics query + alert: `WORKER TIMEOUT` count > 0 in 15 min | See §6 |
| P2 | Alert on **AverageResponseTime > 5 s** for 5 min + **Requests/min** spike | App Service metrics |
| P2 | Dashboard: memory working set + pool checkout (if exposed) + platform_504 event count | Admin → Security events |

---

## 6. Investigation checklist (future 504)

1. **Security event** → read `diagnostics_summary`, `likely_causes`, `worker_metrics.in_flight_requests` (stale paths).
2. **Same UTC window** → `az webapp log tail` or downloaded docker log:
   - `WORKER TIMEOUT`
   - `[STUCK_REQUEST]` / `[SLOW_REQUEST]`
   - `Autorestarting worker`
   - `QueuePool`
3. **App Service metrics** → Requests/min, AverageResponseTime, MemoryWorkingSet, Http5xx (often 0 for gateway 504).
4. **Do not** assume the failed URL is the blocker — search for **incomplete** requests (gaps in access log) before the 504.
5. **Log Analytics** (if IFRC OMS access):

```kusto
AppServiceConsoleLogs
| where TimeGenerated between (datetime(2026-07-09T08:00:00Z) .. datetime(2026-07-09T08:45:00Z))
| where LogMessage contains "WORKER TIMEOUT" or LogMessage contains "STUCK_REQUEST" or LogMessage contains "Platform Error 504"
| project TimeGenerated, LogMessage
| order by TimeGenerated asc
```

---

## 7. Recommended rollout sequence

### Phase 1 — Operations (no deploy, days)

1. Turn on **console logging** in Azure App Service.
2. Add missing Azure app settings: `DB_STATEMENT_TIMEOUT_MS`, `DB_CONNECT_TIMEOUT`, confirm `GUNICORN_*`.
3. Reduce **`GUNICORN_WORKERS`** from 5 → **3** during a low-traffic window; watch memory and latency.
4. Create alert on **`WORKER TIMEOUT`** in log stream / Log Analytics.

### Phase 2 — Application (1–2 sprints)

1. Profile and optimize **`/forms/assignment/<id>`** (largest user-visible win).
2. EmOps: **warm cache** / never block form render on live external API.
3. Matrix auto-load: reduce parallel fan-out on initial page load.

### Phase 3 — Platform hardening

1. Deploy **Redis** (`REDIS_URL`) for sessions and rate limiting.
2. Evaluate **second App Service instance** (scale out).
3. Move **scheduler** to external job runner if not already planned.

### Phase 4 — Observability

1. Cross-worker diagnostic ring buffer in Redis.
2. AGW access log correlation for 504 ↔ backend pool.

---

## 8. Success criteria

| Metric | Target |
|--------|--------|
| `platform_504_gateway_timeout` security events | **< 2 per week** outside known deploy windows |
| `WORKER TIMEOUT` in logs | **0** during business hours |
| `GET /forms/assignment/*` p95 server time | **< 1.5 s** |
| Presence `/sync` p95 (when app healthy) | **< 100 ms** |
| App Service avg response time | **< 1 s** sustained |

---

## 9. References

- Gunicorn config: `Backoffice/config/gunicorn.conf.py` (`GUNICORN_TIMEOUT` default **60 s** — heartbeat/dead-worker detector under gthread, not a request timeout; raised from 25 s after the 2026-07-16 incident where recycle teardown could exceed it)
- Presence API: `Backoffice/app/routes/forms_api.py` (`/presence/assignment/<id>/sync`)
- Platform-error reporter: `Backoffice/app/static/js/lib/platform-error-reporter.js`
- Diagnostics: `Backoffice/app/services/monitoring/platform_error_diagnostics.py`, `request_pressure.py`
- Azure ops script: `azure_webapp_tools.bat` (log tail, SSH, deploy)

---

## 10. Document history

| Date | Author | Change |
|------|--------|--------|
| 2026-07-09 | Engineering | Initial report from 2026-06-30 and 2026-07-09 production investigations |
| 2026-07-15 | Engineering | Shipped fixes for the highest-priority "unnecessary server exhaustion" patterns found while investigating a related AI-documents 502: workflow tour static/CDN offload, `localStorage`-cached notification preferences + WS status checks, and a Gunicorn-thread-budget-aware cap shared across notification/AI-chat/AI-docs WebSockets (with graceful polling/SSE fallback). Added `[WS_POOL]`, `[NOTIF_PREFS_FETCH]`, `[WS_STATUS_FETCH]`, `[WORKFLOW_TOUR_DYNAMIC_HIT]` INFO-level logs and a `worker_metrics.ws_pool` diagnostics field to confirm the fixes in production logs. |
| 2026-07-17 | Engineering | Closed the residual post-deploy `WORKER TIMEOUT` pattern: recycles of workers holding live WebSocket connections hung in interpreter finalization (non-daemon gthread pool threads pinned by `ws.receive()`), leaving a silent zombie until SIGKILL. `worker_exit`/`worker_abort` hooks now hard-exit via `scheduler_lock.hard_exit_if_lingering_threads` when non-daemon threads linger after teardown. Also removed the `GUNICORN_TIMEOUT=25` Azure app setting that had been overriding the 60 s default. |
| 2026-07-17 | Engineering | Presence load reduction + cross-worker fix: `presence.js` idles at 60 s when solo, dedupes tabs via `BroadcastChannel` leader election, and no longer re-nags dismissed warnings on brief flickers; `check_aes_access_light` caches positive (user, aes) results for 5 min so steady-state ticks skip the DB; `presence_store.py` becomes Redis-backed (shared across workers) automatically once `REDIS_URL` is deployed, fixing the probabilistic co-editor visibility of the per-worker in-memory store. |
