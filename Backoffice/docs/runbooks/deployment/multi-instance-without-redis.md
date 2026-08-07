# Multi-Instance App Service Without Redis — Risks & Mitigations

**Status:** Active guidance  
**Last reviewed:** 2026-07-23  
**Last updated:** 2026-07-23 — digest advisory locks + atomic claims implemented (see §3.3)  
**Context:** Production scaled to **2 instances** on **P2v3** (`ifrc-databank-app`); **`REDIS_URL` not configured** (may remain unavailable for budget or infra reasons).

Related: [Azure App Service](azure-app-service.md), [Gateway 504 / worker saturation](../incidents/gateway-504-worker-saturation.md), [Session management](../sessions/session-management.md).

---

## 1. Executive summary

Scaling App Service **out** (more instances) improves capacity and isolates worker-recycle blips, but several subsystems assume **shared state** that today lives in **process memory** or **local `/tmp`**. Without Redis, those subsystems do **not** coordinate across instances.

**Good news:** Core databank operations (login, form entry, API writes) use **signed cookie sessions** and **PostgreSQL** — they do **not** require Redis.

> **Note on Redis sizing misconceptions:** Redis is not only for “millions of sessions.” It addresses coordination and performance at many scales (caching, rate limits, locks, queues, real-time state). The decision depends on latency, traffic patterns, data lifetime, and ops cost — not an arbitrary user count. For this app, the driver is **multi-worker / multi-instance coordination**, not session volume. See [Redis provisioning — §2.1](redis-provisioning.md#21-common-misconception--redis-is-only-for-millions-of-sessions).

**Main gaps without Redis:**

> **Growth context:** Load and traffic are only increasing. Planned next phases migrate the **Indicator Bank** and **FDRS** reporting systems into Network Databank — provision shared coordination (Redis) before that traffic lands on multi-instance deployments. See [Redis provisioning — Growth trajectory](redis-provisioning.md#growth-trajectory--load-is-increasing).

| Area | Cross-instance? |
|------|-----------------|
| Flask login session (cookie) | Yes |
| Form / API persistence (PostgreSQL) | Yes |
| APScheduler ownership (`flock` in `/tmp`) | **No — one scheduler per instance** |
| Flask-Limiter + custom rate limits | **No — per worker memory** |
| Security alert email cooldown | **No — per worker memory** |
| Co-editing presence | **No — per worker memory** (degraded UX only) |
| AI WebSocket connections | **No — per worker memory** |

**Minimum action when running ≥2 instances without Redis:** enable **ARR Affinity (Session affinity) = On** in App Service Configuration.

---

## 2. Risk register

Severity legend: **Critical** → user-facing data or trust impact; **High** → security or duplicate side effects; **Medium** → degraded UX or ops noise; **Low** → observability / edge cases.

| ID | Risk | Level | What happens | Likelihood (2 inst., no Redis) |
|----|------|-------|--------------|--------------------------------|
| R1 | **Duplicate scheduler jobs** | ~~High~~ **Mitigated** | Each instance runs its own APScheduler (`flock` is local to each VM). Cleanup jobs are idempotent. Digest / notification jobs now protected by PG advisory locks + atomic DB claims (deployed 2026-07-23, see §3.3). | **Low** — advisory locks prevent concurrent sweeps |
| R2 | **Digest email race** | ~~Medium~~ **Mitigated** | `send_notification_emails` and `run_fds_access_request_digest_job` each acquire a PG advisory lock before doing any work; per-user `last_digest_sent_at` claim is now an atomic `UPDATE WHERE`. Only one instance wins the slot per user per window. | **Very unlikely** — requires advisory lock and atomic claim to both fail simultaneously |
| R3 | **Weakened rate limiting** | **High** | `RATELIMIT_STORAGE_URI` defaults to `memory://`. Effective limit ≈ **configured × instances × workers** (e.g. 2 × 3 = **6×**). | **Certain** under attack |
| R4 | **Security alert email storm** | **Medium** | Alert cooldown is in-process without Redis → up to **one email per worker per incident** (e.g. 6 emails for 2×3 workers). Events are always logged. | **Possible** during 502/504 bursts |
| R5 | **Co-editing presence inaccurate** | **Low** | Presence store falls back to in-memory per worker. Users on different instances may not see each other in the presence bar. **Form data is unaffected.** | **Likely** during genuine co-editing |
| R6 | **AI WebSocket stickiness** | **Medium** | WS connections are in-memory on one worker. Without affinity, upgrade and later HTTP may hit different instances; client falls back to polling/SSE. | **Possible** for AI chat users |
| R7 | **DB connection budget** | **Medium** | Max connections scale with instances: ~**90 → ~180** (3 workers × (pool 10 + overflow 20) × instances). Still below PostgreSQL `max_connections=250` if unchanged — monitor. | **Certain** when scaled out |
| R8 | **Multi-step admin flows with local files** | **Low** | Flows that store a **local path** in session (e.g. UPR Excel import wizard under `instance/upr_import_uploads`) fail if the next request lands on an instance without that file. `/home` on App Service is often shared, but do not rely on this without verification. | **Unlikely** if ARR Affinity on |
| R9 | **Uneven load with ARR Affinity** | **Low** | Sticky users reduce per-request spreading; capacity still scales with **user count**, not requests per user. | **Certain** when affinity on |
| R10 | **Gateway 502 under stress** | **Medium** | Worker `max_requests` recycles under high load cause AGW 502s (observed 2026-07-23: 35×502 at 50 VU, single instance). Extra instances **reduce blast radius**; Redis does **not** fix this directly. | **Possible** during load tests / peaks |

---

## 3. Proposed solutions (Redis unavailable)

Actions grouped by effort. Prefer **Immediate** before the next reporting peak or load test.

### 3.1 Immediate (portal / config, no deploy)

| Action | Addresses | Detail |
|--------|-----------|--------|
| **Enable ARR Affinity = On** | R5, R6, R8 | Azure Portal → App Service → Configuration → General settings → **Session affinity**. Required handbook default when `REDIS_URL` is unset. |
| **Confirm instance count** | R7, R10 | Scale out only when needed; scale back to 1 after load tests if cost-sensitive. |
| **Monitor scheduler duplication** | R1, R2 | Tail logs: `azure_webapp_tools.bat prod logs`. Grep `[SCHED_JOB] send_digest_emails`, `Email notification digests sent`. Watch for pairs within the same minute. |
| **Monitor DB connections** | R7 | Azure PostgreSQL metrics: active connections vs `max_connections`. Alert if sustained >70% of limit. |

### 3.2 Short term (ops / process)

| Action | Addresses | Detail |
|--------|-----------|--------|
| **Load-test tiers** | R10 | Default prod profile: **10 VU / 60 s**. Stress (50 VU) only with ops approval; expect ~1% gateway 502 on single instance; re-test after scale-out. |
| **Temporary scale-out** | R10 | Scale to 2 instances **only during** formal capacity tests, then scale back to 1 if budget requires. |
| **Review digest window** | R2 | `NOTIFICATION_DIGEST_TRIGGER_WINDOW_MINUTES` and `last_digest_sent_at` idempotency — ensure window covers scheduler interval (default 5 min job, 60 min window). |
| **Incident playbooks** | R4 | During 502 storms, expect multiple alert emails (cooldown per worker). Triage via Security events + logs, not email count alone. |

### 3.3 Medium term (deploy / infra — still no Redis)

| Action | Addresses | Detail |
|--------|-----------|--------|
| ✅ **DB advisory lock on digest sweeps** *(done 2026-07-23)* | R1, R2 | `send_notification_emails` and `run_fds_access_request_digest_job` each acquire a PostgreSQL session advisory lock (`pg_try_advisory_lock`) before doing any work. The second instance that fires concurrently skips immediately with a DEBUG log. Lock IDs: `DIGEST_EMAIL_LOCK_ID` (default `702348`) and `FDS_DIGEST_LOCK_ID` (default `702349`) — overridable as Azure app settings. |
| ✅ **DB advisory lock on AI document batch jobs** *(done 2026-08)* | R1 | `run_ai_job` in `app/services/ai/ai_job_runner.py` acquires a session advisory lock per job (`pg_try_advisory_lock`) before processing items. Lock IDs are derived from `950_000_000 + (crc32(job_id) % 49_000_000)` — namespace clear of digest/RBAC locks (`702348`, `702349`, `915037121`, `7474242`). A second worker/instance skips starting the runner when the lock is held elsewhere. |
| ✅ **Atomic `last_digest_sent_at` claim** *(done 2026-07-23)* | R2 | `send_daily_digest` and `send_weekly_digest` replaced the non-atomic read-then-write with an atomic `UPDATE notification_preferences SET last_digest_sent_at = NOW() WHERE user_id = :id AND (last_digest_sent_at IS NULL OR last_digest_sent_at < :cutoff)`. Only the instance that gets `rowcount == 1` sends; all others return `False`. Belt-and-suspenders if the session lock is released mid-sweep. |
| **External scheduler** (optional, future) | R1 | Set `SCHEDULER_DISABLE_ALL_WORKERS=true` on **all** web instances and run APScheduler jobs in **Azure Container Job** or **Function**. Current DB locks make this optional while staying on App Service. |
| **Document rate-limit expectations** | R3 | Treat in-memory limits as **per-worker**; tune configured values down if abuse is a concern (e.g. divide by `instances × workers`). |

### 3.4 When Redis becomes available (future)

| Action | Addresses | Detail |
|--------|-----------|--------|
| Set **`REDIS_URL`** | R3, R4, R5 | Shared rate limits, fleet-wide alert cooldown, cross-worker presence. See [Redis provisioning](redis-provisioning.md): **Azure Managed Redis Balanced B0 (West Europe)**. |
| Set **`RATELIMIT_STORAGE_URI`** | R3 | Can mirror `REDIS_URL` or use a separate DB index. |
| **Turn ARR Affinity Off** | R9 | Better load distribution once sessions/rate limits/presence are Redis-backed. |
| **Redis scheduler lock** | R1 | Optional enhancement; external scheduler (§3.3) may still be preferable for heavy jobs. |

---

## 4. What does *not* require Redis

These work correctly across multiple instances today:

- **Authentication** — signed cookie sessions (`SESSION_*` in config; no server-side session store).
- **Authorization / RBAC** — PostgreSQL.
- **Form submission and matrix data** — PostgreSQL.
- **Notification HTTP API** — prod uses HTTP polling for notifications (notification WebSockets disabled in production config).
- **Blob / Azure storage uploads** — when using `azure_blob` backend (not local path only).

---

## 5. Capacity notes (2026-07-23 load test)

Heavy prod run (`run-20260723-162830`, 50 VU, 300 s, single instance):

- **0.75% errors** — all **35 failures were HTTP 502** from Application Gateway (not Flask 5xx, not WAF).
- Prod console logs: **10× `recycle(max_requests)`** in the test window; **0× `WORKER TIMEOUT`**.
- Root cause class: **worker recycle + thread saturation**, not missing Redis.

Scaling to 2 instances **helps** R10 (isolation) but **introduces** R1–R5 unless mitigations in §3 are applied.

Current prod platform (verify in Azure before changes):

| Setting | Typical value |
|---------|----------------|
| Plan | P2v3, 2 instances (after scale-out) |
| `GUNICORN_WORKERS` | 3 |
| `SQLALCHEMY_POOL_SIZE` | 10 |
| `REDIS_URL` | unset |
| `DB_STATEMENT_TIMEOUT_MS` | code default **18000** ms (18 s) if unset in Azure |
| `DB_CONNECT_TIMEOUT` | code default **10** s if unset in Azure |

---

## 6. Decision checklist

Before scaling to **N ≥ 2** instances without Redis:

- [ ] ARR Affinity **On**
- [ ] PostgreSQL connection headroom checked for **N × 90** max app connections
- [ ] Scheduler duplication monitoring in place (§3.1)
- [x] Digest email deduplication: PG advisory lock + atomic claim deployed (§3.3) — no longer requires external scheduler or Redis
- [ ] Load-test profile documented (smoke vs stress VU)

Before turning ARR Affinity **Off**:

- [ ] `REDIS_URL` configured and verified (`Presence store: using Redis backend` in logs)
- [ ] `RATELIMIT_STORAGE_URI` or `REDIS_URL` set for Flask-Limiter
- [ ] Presence / AI WS tested under multi-instance load

---

## 7. Related documentation

- [Redis provisioning](redis-provisioning.md) — **Azure Managed Redis Balanced B0** (West Europe, CHF estimates)
- [Azure App Service §3a — recommended settings](azure-app-service.md#3a-recommended-application-settings-avoid-502504)
- [Gateway 504 / worker saturation](../incidents/gateway-504-worker-saturation.md)
- [Platform 502 DB pool incident (2026-07-22)](../../../../docs/handovers/2026-07-22-platform-502-db-pool-alert-storm-incident.md)
- [Session management](../sessions/session-management.md)
