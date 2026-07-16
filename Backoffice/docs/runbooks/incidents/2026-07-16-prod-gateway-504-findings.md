# Prod Gateway 504 — Investigation Findings (2026-07-16)

**Status:** Open — agent handoff  
**Environment:** Production (`ifrc-databank-app`, RG `ifrcpunifiedplanning-rg001`, West Europe)  
**Investigation window:** **15:55–17:55 CEST** (13:55–15:55 UTC), ~2 hours  
**Log source:** `az webapp log download` via `azure_webapp_tools.bat`  
**Local log archive:** `Backoffice/instance/logs/prod-hour-20260716-1747/`  
**Related playbook:** [Gateway 504 / worker saturation](gateway-504-worker-saturation.md)

---

## 1. Executive summary

Production experienced a **sustained worker-saturation incident** over ~2 hours on **2026-07-16**. Users saw **44 platform-level HTTP 504** errors (Azure/gateway timeouts, not Flask 5xx). Failed URLs are predominantly **lightweight polling endpoints** (notifications, presence sync, profile lookups) — classic **canary** behaviour per the known failure mode.

**Probable blocker (new signal this incident):** `GET /admin/api/translation_services` hung **15–23+ seconds** on multiple workers (**11 `[STUCK_REQUEST]` warnings**), coinciding with **worker kills at 16:05 and 16:17 CEST**. The 504 cluster at **16:27 CEST** likely cascaded from ongoing worker pressure.

**No 502 or 503** platform errors in the window.

---

## 2. Key metrics

| Metric | Value |
|--------|------:|
| Platform 504 events | **44** |
| Unique endpoints affected | **20** |
| Worker timeouts (`WORKER TIMEOUT`, 25s) | **3** |
| Stuck-request warnings (`[STUCK_REQUEST]`) | **11** (all same path) |
| Platform 502 / 503 | **0** |

### Likely causes (from platform-error diagnostics, per event)

| Cause | Count |
|-------|------:|
| Queue wait / hung request on another worker | 32 |
| DB connection pool exhausted (5/5–7/5 checked out) | 9 |
| Elevated per-worker traffic | 3 |

Reporter workers often showed **0 in-flight** on the failing worker — consistent with collateral damage. **`REDIS_URL` is not set** in prod, so cross-worker diagnostics are per-worker only.

---

## 3. Timeline (CEST)

| Time | Event |
|------|-------|
| **15:55–16:05** | `GET /admin/api/translation_services` stuck 15s → 23s+ on workers pid 10337, 10068 |
| **16:05:57** | `WORKER TIMEOUT` pid **10337** (scheduler_owner=False) |
| **16:17:58** | `WORKER TIMEOUT` pid **10068** (scheduler_owner=True) |
| **16:27:54–16:32:43** | **Incident onset cluster** — 8× 504, mostly `/notifications/api/preferences` |
| **16:35–16:36** | 4× 504 — preferences, EmOps list-data, presence 1616 |
| **16:40–16:42** | 8× 504 — admin templates, presence 1630, completion-rate, notifications burst |
| **16:45–16:57** | Intermittent 504s on form/matrix/profile endpoints |
| **17:05:25** | `WORKER TIMEOUT` pid **101** |
| **17:05:38** | 504 on presence 1627/sync (immediately after worker kill) |
| **17:11:57–17:12:17** | **Worst burst** — 7× 504; diagnostics: DB pool **7/5**, traffic **~112 req/min** on reporting worker |
| **17:18:49** | 2× 504 — preferences + admin profile-summary |
| **17:42:06** | Isolated 504 on `/notifications/api/count` |

---

## 4. Endpoints that received 504 (normalized paths)

| Hits | Endpoint | Role |
|-----:|----------|------|
| **18** | `/notifications/api/preferences` | Page-load poll (should be localStorage-cached since 2026-07-15) |
| 3 | `/api/forms/presence/assignment/1616/sync` | Presence canary |
| 3 | `/notifications/api` | Notification list poll |
| 2 | `/admin/api/users/profile-summary` | Admin UI |
| 2 | `/api/users/profile-summary` | Profile lookup |
| 2 | `/api/v1/csrf-token` | Page-load dependency |
| 1 | `/admin/plugins/emergency_operations/api/list-data` | EmOps plugin |
| 1 | `/admin/templates/23/variables/options` | Admin template editor |
| 1 | `/api/forms/presence/assignment/1630/sync` | Presence |
| 1 | `/api/forms/assignment/1630/completion-rate` | Form UI |
| 1 | `/notifications/api/stream/status` | WS fallback check (should be cached 5 min since 2026-07-15) |
| 1 | `/api/v1/matrix/auto-load-entities/batch` | Matrix load |
| 1 | `/api/forms/assignment/1616/completion-rate` | Form UI |
| 1 | `/api/v1/variables/resolve` | Form UI |
| 1 | `/forms/matrix/search-rows` | Matrix search |
| 1 | `/api/ai/documents/workflows/.../tour` | AI workflow tour |
| 1 | `/api/forms/presence/assignment/1611/sync` | Presence |
| 1 | `/api/forms/dynamic-indicators/render-pending` | Form render |
| 1 | `/api/forms/presence/assignment/1627/sync` | Presence |
| 1 | `/notifications/api/count` | Notification badge |

**Do not treat these URLs as root cause.** They are victims of worker/DB pool exhaustion.

---

## 5. Root-cause signals for follow-up agent

### 5.1 Primary suspect: `/admin/api/translation_services`

- **11** `[STUCK_REQUEST]` / `[STUCK_REQUEST_CRITICAL]` entries in the 2-hour window
- Request duration **15s (warning) → 23s (critical)** before gateway/worker kill
- DB pool on stuck worker: **1–4/5** checked out (not always pool-saturated on the stuck worker itself)
- Access log shows successful responses but with **very high durations** earlier in the day:
  - `GET /admin/api/translation_services` — **130303 ms** (~130s) at 16:11 CEST
  - **339196 ms** (~339s) at 16:23 CEST
- Endpoint: `utilities.api_translation_services`

**Agent action:** Profile this route — what external call or DB query blocks for 25s+? Check auto-translator service, timeout config, and whether admin indicator-bank pages trigger concurrent calls.

### 5.2 Notification preferences still top 504 surface

Despite client-side `localStorage` cache (shipped 2026-07-15), `/notifications/api/preferences` accounts for **41%** of 504s. Possible explanations:

- Users on **cached old JS** (no hard refresh after deploy)
- Cache bypass paths (admin pages, service worker, direct fetches)
- Saturation so severe that even fast/cacheable requests queue past gateway timeout
- `[NOTIF_PREFS_FETCH]` log volume in this window — **grep prod logs to confirm cache hit rate**

**Agent action:** Grep `default_docker.log` for `[NOTIF_PREFS_FETCH]` and `[WS_STATUS_FETCH]` in 15:55–17:55 CEST. Compare against `[WORKFLOW_TOUR_DYNAMIC_HIT]`.

### 5.3 DB pool pressure at peak

Peak burst (17:11–17:12) reported **DB pool 7/5** (overflow 2–3). Suggests concurrent long-running requests holding connections.

**Agent action:** Review `SQLALCHEMY_POOL_SIZE`, `SQLALCHEMY_MAX_OVERFLOW`, and whether translation_services or form/matrix endpoints hold connections across slow I/O.

### 5.4 Worker recycle / scheduler interaction

All 3 worker timeouts logged `[was in recycle — scheduler shutdown likely blocked]`. Pids 10337 and 10068 were `scheduler_owner=True/False` respectively.

**Agent action:** Review recent changes to `scheduler_lock.py` and gunicorn `max_requests` recycle path — see git status on `Backoffice/app/scheduler_lock.py`, `Backoffice/config/gunicorn.conf.py`, `Backoffice/app/scheduler.py`.

---

## 6. Incident clusters (for log correlation)

Events grouped when within **2 minutes**:

| # | Window (CEST) | Events | Top paths |
|---|---------------|-------:|-----------|
| 1 | 16:27:54–16:32:43 | 8 | preferences(6), profile-summary(2) |
| 2 | 16:35:00–16:36:28 | 4 | preferences(2), EmOps(1), presence 1616(1) |
| 3 | 16:40:02–16:42:58 | 8 | preferences(2), templates, presence 1630, completion-rate, notifications |
| 4 | 16:45:23–16:45:28 | 5 | form/matrix/profile batch |
| 5 | 16:50:16 | 1 | preferences |
| 6 | 16:52:48–16:53:29 | 2 | preferences, AI tour |
| 7 | 16:55:57–16:57:04 | 4 | presence, csrf-token, preferences |
| 8 | 17:04:09–17:05:38 | 2 | dynamic-indicators, presence 1627 |
| 9 | **17:11:57–17:12:17** | **7** | preferences(3), notifications/api(2), presence, csrf |
| 10 | 17:18:49 | 2 | preferences, admin profile-summary |
| 11 | 17:42:06 | 1 | notifications/api/count |

---

## 7. Recommended actions (prioritized)

### P0 — Investigate blocker

1. **Trace `/admin/api/translation_services`** — reproduce on prod/staging; add timing logs or profile DB/external calls; set hard timeout < `GUNICORN_TIMEOUT` (25s).
2. **Read access logs** around 16:11 and 16:23 for translation_services multi-minute responses — identify user/session and upstream dependency.

### P1 — Confirm mitigation effectiveness

3. Grep prod logs for `[NOTIF_PREFS_FETCH]`, `[WS_STATUS_FETCH]`, `[WS_POOL]` in incident window — verify 2026-07-15 client/server fixes are active.
4. Check whether **2026-07-14 deploy** (deployment id `63c39ce34fd3755b39a3aaa4b866abb9f51545cb` at 16:24 UTC / 18:24 CEST on 2026-07-14) is the running build and includes cache/WS changes.

### P2 — Capacity & observability

5. Evaluate enabling **`REDIS_URL`** in prod for cross-worker platform-error diagnostics (called out in every 504 event).
6. Review DB pool sizing and long-transaction patterns during admin + form concurrent usage.
7. Review scheduler + worker recycle interaction (`scheduler_lock.py`, `gunicorn.conf.py`) — worker kills during recycle may amplify outages.

### P3 — Alerting

8. Add/run Log Analytics alert: `WORKER TIMEOUT` count > 0 in 15 min (per [gateway-504 runbook](gateway-504-worker-saturation.md) §6).

---

## 8. Log investigation commands

```powershell
# From repo root — tail live (won't help historical; use download for incidents)
.\azure_webapp_tools.bat prod logs

# Download fresh archive
az account set --subscription 3e33b4c1-ada7-4922-9113-b9e41eaf1797
az webapp log download --name ifrc-databank-app --resource-group ifrcpunifiedplanning-rg001 --log-file prod-logs.zip
```

```powershell
# Search downloaded docker log (adjust path after extract)
$docker = "Backoffice\instance\logs\prod-hour-20260716-1747\extracted\LogFiles\2026_07_16_ln1mdlwk000EYI_default_docker.log"

rg "Platform Error 504|WORKER TIMEOUT|STUCK_REQUEST|translation_services|NOTIF_PREFS_FETCH|WS_STATUS_FETCH|WS_POOL" $docker
```

---

## 9. Files & references

| Item | Path |
|------|------|
| This findings doc | `Backoffice/docs/runbooks/incidents/2026-07-16-prod-gateway-504-findings.md` |
| Recurring pattern runbook | `Backoffice/docs/runbooks/incidents/gateway-504-worker-saturation.md` |
| Azure ops script | `azure_webapp_tools.bat` |
| Downloaded log zip | `Backoffice/instance/logs/prod-hour-20260716-1747/prod-logs.zip` |
| Application docker log | `.../extracted/LogFiles/2026_07_16_ln1mdlwk000EYI_default_docker.log` |
| Suspect route (verify) | `utilities.api_translation_services` → `/admin/api/translation_services` |
| Recent git changes (local) | `scheduler_lock.py`, `gunicorn.conf.py`, `scheduler.py`, `auto_translator.py` |

---

## 10. Handoff note for next agent

The failure mode matches the **documented gateway 504 / worker saturation pattern**. This incident adds a **specific blocker candidate**: `/admin/api/translation_services` hanging 23s–339s. Fix or timeout that endpoint first; then verify notification-preference caching is live in prod. Do **not** optimize presence sync or notification routes in isolation — they are symptoms.

**Success criteria after fix:**

- `platform_504_gateway_timeout` events < 2/week outside deploy windows
- `WORKER TIMEOUT` = 0 during business hours
- `[STUCK_REQUEST]` on translation_services eliminated or bounded < 5s
