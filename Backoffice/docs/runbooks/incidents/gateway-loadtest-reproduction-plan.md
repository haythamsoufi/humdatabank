# Gateway timeout reproduction — end-to-end plan

**Status:** Proposed  
**Related:** [Gateway 504 / worker saturation](gateway-504-worker-saturation.md), [2026-07-16 findings](2026-07-16-prod-gateway-504-findings.md)  
**Goal:** Reproduce production-like **502/504 gateway timeouts** under controlled load, then measure whether app fixes (and later Redis) improve behaviour — without relying on production as the only test bed.

---

## 1. Why this exists

Production (behind Azure Application Gateway) has shown intermittent **502/504** under modest concurrency (~20 users). Staging has often looked fine because:

1. Staging is **not behind App Gateway** (different timeout / edge behaviour).
2. Existing load tests mostly hit **API-key HTTP** paths, not **session + WebSocket + browser polls**.
3. Prod load testing through AGW is constrained and risky.

So failures that depend on **gateway backend timeout (~30s) + Gunicorn `gthread` + long-lived WebSockets** never surface in pink-path staging.

This plan closes that gap in three layers:

| Layer | What | Fidelity |
|-------|------|----------|
| A | Local Docker + nginx “AGW-sim” | Timeout / WS proxy approx. |
| B | Automated real-user-like traffic | Concurrency + pinning |
| C | Staging behind real App Gateway (+ optional Redis before/after) | Production-like proof |

Redis remains a **separate workstream**. It must not be treated as the fix for worker/WS saturation; it is measured in layer C only after baseline saturation tests exist.

---

## 2. Failure mode we are trying to reproduce

```text
Browsers (N users, multiple tabs)
  → edge (AGW or nginx sim)  — backend request timeout ≈ 30s
  → Gunicorn gthread (e.g. 3 workers × 8 threads)
       ├─ long-lived /api/notifications/ws  (1 thread each, for lifetime)
       ├─ background polls (presence, prefs, status)
       └─ heavier pages (forms / admin)
  → when threads/DB pool saturate, light requests queue
  → edge returns 502/504 while App Service Http5xx may stay ~0
```

**Success = reproduction**, not perfection. We want:

- Client-visible **502/504** (or equivalent gateway timeout) on light endpoints
- Correlation with open WebSocket count / worker pressure
- Backend logs showing saturation (`WORKER TIMEOUT`, `[WS_POOL]`, queueing), not only edge silence

---

## 3. Layer A — Local App Gateway simulation

### 3.1 What we can and cannot do

- **Cannot** run Azure Application Gateway locally (managed Azure service; no official emulator).
- **Can** put **nginx / Caddy / Traefik** in front of the local Docker backoffice and mimic the behaviours that matter for this incident class.

### 3.2 Behaviours to mimic

| Prod (AGW / platform) | Local proxy setting (sketch) |
|-----------------------|------------------------------|
| Backend request timeout ~30s | `proxy_read_timeout` / `proxy_send_timeout` **30s** |
| Long-lived notification WebSockets | Separate `location` with Upgrade headers; long WS timeouts (e.g. 3600s) |
| Keepalive vs Gunicorn | Proxy keepalive **below** `GUNICORN_KEEPALIVE` (prod default 75) |
| Sticky sessions (ARR Affinity) | Optional sticky cookie / IP hash (nice-to-have) |

What local sim will **not** prove: exact WAF rules, AGW probe draining, Private Link, or identical 502/504 metric shapes. Treat nginx as a **timeout + WS proxy simulator**.

### 3.3 Compose shape (idea)

Add an optional compose profile (e.g. `gateway`) that:

1. Leaves `backoffice` on an internal port only (or still expose 5000 for direct debug).
2. Exposes **nginx on 8080** as the only “user-facing” URL for load tests.
3. Mounts a small config, e.g. `local/nginx-appgw-sim.conf`.

Sketch:

```nginx
upstream backoffice {
  server backoffice:5000;
  keepalive 32;
}

server {
  listen 80;

  location / {
    proxy_pass http://backoffice;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header Connection "";
    proxy_read_timeout 30s;
    proxy_send_timeout 30s;
    proxy_connect_timeout 10s;
  }

  location /api/notifications/ws {
    proxy_pass http://backoffice;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_read_timeout 3600s;
    proxy_send_timeout 3600s;
  }
}
```

**Rule for tests:** generate traffic against `http://localhost:8080`, not `:5000`. Direct-to-app bypasses the timeout behaviour we care about.

### 3.4 Local app settings for a fair fight

Align local gunicorn with prod-ish knobs when testing saturation:

- `GUNICORN_WORKERS=3` (or same as prod)
- Threads: code default 8 unless overridden
- `GUNICORN_TIMEOUT` unset → code default **60** (heartbeat / recycle; not the client 504 timer)
- No Redis unless intentionally testing the Redis workstream later

---

## 4. Layer B — Automate traffic like real users

HTTP-only API-key smoke tests will **not** reproduce this class of failure. Traffic must look like browsers.

### 4.1 Virtual-user behaviour (per “user”)

Each virtual user should roughly:

1. Authenticate (staging test account or captured session cookie; local quick-login / test users).
2. Open 1–2 “tabs” (parallel clients sharing the same session if needed).
3. Hold **`/api/notifications/ws`** open for the whole scenario.
4. Poll light endpoints on real-ish intervals (presence sync, notification prefs/status — whatever the UI still does after current deferrals).
5. Periodically hit heavier pages (`/forms/assignment/<id>`, admin pages) to create blocking work.
6. Run **15–25 concurrent users** for several minutes (prod pain was around ~20).

### 4.2 Tooling (use what we already have)

| Tool | Location | Best use |
|------|----------|----------|
| **k6** | `k6-load-tests/` | Scale HTTP; today mostly API-key — extend with **session cookie + WS** scenario |
| **Locust + Azure Load Testing** | `Backoffice/azure/loadtest/` | Authenticated routes via `LOADTEST_SESSION_COOKIE`; good for staging/Azure runs |
| **Playwright** | existing browser testing | High-fidelity WS + JS polls for a **smaller** N of real browsers |

Recommended combo:

- **Playwright (few browsers)** for fidelity (real WS + layout polls)
- **k6 or Locust (many VUs)** for concurrency and gateway timeouts
- Always through **nginx sim** locally, or **real AGW** on staging

### 4.3 New scenario to add (gap today)

Working title: `gateway-ws-saturation` (k6 and/or Locust).

Must include:

- Session auth (not only `K6_BACKOFFICE_API_KEY`)
- WebSocket connect + keep-alive for scenario duration
- Light polls that historically showed up in 504 reporters
- Optional heavy GET burst
- Thresholds / metrics: rate of **502/504**, p95 latency, open WS count if available

Keep existing Phase 1 API-key scenarios for smoke; do not overload them with this purpose.

### 4.4 Auth constraints

- Prefer **staging test accounts** or short-lived captured cookies.
- Prod SSO makes unattended prod load tests painful — **default target is staging or local**, not prod.
- Never run saturation tests against prod without explicit ops/infra sign-off.

---

## 5. Layer C — Staging behind real App Gateway

Local nginx answers “can we saturate workers and trip a 30s edge timeout?”  
Staging AGW answers “does this look like prod?”

### 5.1 Prerequisites (infra)

1. Put **staging** behind Application Gateway (same class of backend timeout / WS path as prod, as far as practical).
2. Point health probes at a cheap health endpoint (not a heavy HTML page), consistent with prod hardening advice.
3. Provision **Azure Managed Redis Balanced B0 (West Europe)** for staging when ready for the Redis workstream ([SKU / CHF estimates](../deployment/redis-provisioning.md)) — optional for the *first* saturation baseline.

### 5.2 Test matrix

| Run | Edge | Redis | Purpose |
|-----|------|-------|---------|
| Baseline | Staging AGW | Off | Reproduce 502/504 + capture worker/WS signals |
| After app fixes | Staging AGW | Off | Prove WS budget / recycle / deferral changes help |
| Redis on | Staging AGW | On | Measure shared-state / caching / diagnostics gains only |
| Fail-open | Staging AGW | Kill Redis mid-test | Confirm app stays up (in-memory fallback) |

Share a short before/after report (error rate, p95, WS count, `[WS_POOL]` / worker timeout counts).

### 5.3 Why AGW on staging is non-negotiable for confidence

Without AGW:

- Clients may wait longer than prod’s ~30s edge cut-off.
- 504 shape and timing differ → false confidence (“staging is fine”).
- Prod-only reproduction continues.

---

## 6. End-to-end workflow

```text
1. Implement local nginx AGW-sim (compose profile)
2. Add session+WS saturation scenario (k6 and/or Locust)
3. Run locally against :8080 until 502/504 (or clear saturation signals) reproduce
4. Infra: staging behind AGW
5. Re-run same scenario against staging AGW URL (baseline)
6. Ship / verify app-side worker & WS fixes; re-run (compare)
7. Enable staging Redis; re-run before/after + fail-open
8. Only then discuss prod Redis + any plan-size changes
```

Parallel (already agreed with infra): continue **gateway/worker saturation** app fixes independently of Redis.

---

## 7. Observability during a run

Collect at least:

**Client / load tool**

- Count of 502 / 504 / timeouts
- Latency percentiles for light vs heavy endpoints
- Number of open WebSockets (if the tool can report it)

**App logs / diagnostics**

- SSH snapshot (no Redis required; uses shared FS mirror):  
  `cd /app && python scripts/ops/check_gunicorn_pressure.py`  
  During an incident: `python scripts/ops/check_gunicorn_pressure.py --watch 60 --interval 2`
- `[WS_POOL]`, `[NOTIF_PREFS_FETCH]`, `[WS_STATUS_FETCH]` (or successors)
- `WORKER TIMEOUT` / recycle / `[SCHED_SHUTDOWN]` / `[WORKER_EXIT]`
- Platform-error security events with worker-pressure snapshots
- DB pool pressure notes when present

**Edge**

- Local: nginx access/error logs (upstream timed out)
- Staging: AGW access logs (TimeTaken, 502/504, WS 101 closes) + App Service metrics (note: Http5xx may stay 0 while clients see gateway 504)

---

## 8. Definition of done

This plan is successful when:

1. Local AGW-sim + automated traffic can **reliably stress** the same failure class (or prove it is fixed under that stress).
2. Staging behind **real AGW** can run the **same scenario** for production-like proof.
3. App-side mitigations have a **before/after** number, not only anecdote.
4. Redis (if enabled) has a **separate** before/after and a documented fail-open result — not blended into “we turned everything on and hope.”

---

## 9. Out of scope (for this document)

- Implementing the nginx profile or the new k6/Locust scenario (follow-up engineering tasks).
- Prod Redis cutover.
- Downgrading App Service SKU (only consider after staging evidence).
- Full WAF rule parity locally.

---

## 10. References

- Incident pattern: [gateway-504-worker-saturation.md](gateway-504-worker-saturation.md)
- Jul 16 prod findings: [2026-07-16-prod-gateway-504-findings.md](2026-07-16-prod-gateway-504-findings.md)
- Existing k6 suite: [`k6-load-tests/README.md`](../../../../k6-load-tests/README.md)
- Azure / Locust loadtest: [`Backoffice/azure/loadtest/`](../../../azure/loadtest/)
- Gunicorn / AGW timeout notes: [Developer handbook](../../../../docs/DEVELOPER-HANDBOOK.md) (Gunicorn / App Service sections)
