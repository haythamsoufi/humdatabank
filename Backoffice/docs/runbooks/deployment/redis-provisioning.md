# Redis provisioning — IFRC Network Databank Backoffice

**Application:** IFRC Network Databank Backoffice (repository: Humanitarian Databank Backoffice)  
**Status:** Active guidance  
**Last reviewed:** 2026-07-29  
**Audience:** Infrastructure / platform team and application engineers  
**Region / currency for estimates:** **West Europe**, **CHF** (Swiss Franc)

Related: [Multi-instance without Redis](multi-instance-without-redis.md), [Azure App Service](azure-app-service.md), [redis-infrastructure-request.docx](redis-infrastructure-request.docx).

Pricing source: [Azure retail prices API](https://prices.azure.com/api/retail/prices) (`currencyCode=CHF`, `armRegionName=westeurope`, July 2026). Confirm final figures in the [Azure pricing calculator](https://azure.microsoft.com/en-us/pricing/calculator/) for your agreement.

---

## 1. Short answer

**Provision [Azure Managed Redis](https://azure.microsoft.com/en-us/pricing/details/managed-redis/), Balanced tier, B0 (1 GB).**

- **Production:** two-node high availability (Microsoft recommendation)
- **Staging:** single-node B0 acceptable (no HA)
- **Region:** West Europe (same as App Service / PostgreSQL)
- **Connect:** `REDIS_URL=rediss://<host>:6380/0` via Private Link

The Backoffice uses standard Redis over `redis-py` — no Azure-specific SDK and no Redis Modules.

---

## 2. Why Azure Managed Redis (not Azure Cache for Redis)

| | **Azure Managed Redis** (recommended) | **Azure Cache for Redis** (legacy) |
|---|---|---|
| Pricing | [managed-redis](https://azure.microsoft.com/en-us/pricing/details/managed-redis/) | [cache](https://azure.microsoft.com/en-us/pricing/details/cache/) |
| Smallest SKU | **Balanced B0 — 1 GB** | Standard C0 — 250 MB |
| Lifecycle | Current product for new workloads | Retiring **30 September 2028** |
| Our choice | **Primary** | Not requested — avoid new provisioning |

Both expose a normal Redis endpoint; the app connects only via `REDIS_URL`.

---

## 2.1 Common misconception — “Redis is only for millions of sessions”

**Redis is not only useful for systems with millions of sessions.** It solves performance and coordination problems at almost any scale. Even a small application can use Redis for:

- Caching expensive database queries
- Storing sessions (when server-side sessions are chosen)
- Rate limiting
- Temporary / TTL-bound data
- Background job queues
- Distributed locks
- Real-time features (presence, pub/sub)

**The decision should be based on** latency requirements, traffic patterns, data lifetime, and operational complexity — **not an arbitrary session count.** At lower scale, Redis may improve response times and reduce database load. At very small scale, though, it can also be unnecessary infrastructure; the real question is whether the benefits justify running and maintaining it.

**For the IFRC Network Databank Backoffice specifically:**

| Factor | Our situation |
|--------|----------------|
| Session storage | **Not** the driver — signed HTTP cookies + PostgreSQL; no server-side session store in Redis |
| Why we want Redis | **Multi-worker / multi-instance coordination** — rate limits, presence, alert cooldowns, diagnostics must be shared when App Service scales out |
| Scale | Tens to low hundreds of concurrent users — need is driven by **worker × instance count**, not session volume |
| Working set | Kilobytes to low megabytes of TTL keys |
| Cost vs benefit | ~CHF 22/month (prod HA) vs operating degraded per-worker fallback and keeping ARR Affinity on |

Redis here is a **shared notice board between workers**, not a warehouse for millions of filing cabinets — but the notice board matters as soon as more than one process must agree on the same counter or status.

### Growth trajectory — load is increasing

The Backoffice is not a static workload. **Load and traffic are only increasing** as the IFRC Network Databank becomes the consolidating platform for humanitarian reporting.

| Upcoming phase | Expected impact |
|----------------|-----------------|
| **Indicator Bank migration** | More indicator definitions, history, semantic search (pgvector), and admin API traffic through this system |
| **FDRS migration** | FDRS form templates, submissions, validation, and export pipelines move into Network Databank — higher peaks during reporting cycles |

Both phases add concurrent users, database load, background jobs, and co-editing sessions. **Redis should be provisioned before that growth lands on a multi-instance deployment without shared coordination** — not retrofitted after Indicator Bank and FDRS traffic is already live.

---

## 3. What the application needs from Redis

Redis is **not** used for user sessions or business data. It holds **ephemeral cross-worker coordination** only:

| Subsystem | Redis usage | Commands (typical) |
|-----------|-------------|-------------------|
| Rate limiting / Flask-Limiter | Shared counters | `INCR`, TTL keys |
| Form co-editing presence | One sorted set per assignment | `ZADD`, `ZREMRANGEBYSCORE`, `ZRANGE` |
| Security alert cooldown | Atomic claim per event type | `SET … NX EX` |
| AI WebSocket rate limits / daily quotas | Shared counters | `INCR`, TTL keys |
| 502/504 diagnostics (optional) | Cross-worker pressure hashes | `HSET`, `HGETALL`, TTL |

**Requirements:**

- Standard Redis 6/7 protocol (no Redis Modules)
- No persistence required (TTL-bound keys)
- **Private Link** from App Service VNet (West Europe)
- TLS (`rediss://`)
- **Fail-open:** app keeps serving if Redis is down (in-memory fallback per worker)

**Capacity today:** kilobytes to low megabytes of keys; ~3 Gunicorn workers × N instances → well under connection limits.

---

## 4. Recommended SKUs (West Europe)

### Production

| Setting | Value |
|---------|--------|
| Product | **Azure Managed Redis** |
| Tier | **Balanced** |
| SKU | **B0 — 1 GB**, **two-node HA** |
| Region | **West Europe** |
| Networking | **Private Link** |
| App setting | `REDIS_URL=rediss://<host>:6380/0` |

### Staging

| Setting | Value |
|---------|--------|
| Product | **Azure Managed Redis Balanced B0** |
| HA | **Single-node** (dev/test; no production SLA) |
| Region | **West Europe** |

We do **not** need B1, B3, Memory Optimized, Compute Optimized, Flash, persistence, or clustering at current scale.

---

## 5. Cost estimates (West Europe, CHF)

Public PAYG list prices (retail API, July 2026). Actual invoice may differ by EA/CSP agreement.

| Resource | Configuration | ~CHF / month |
|----------|---------------|--------------|
| **Managed Redis B0** | Staging — **one node** | **~11** |
| **Managed Redis B0** | Production — **two-node HA** | **~22** |
| App Service **P2 v3** (plan) | One instance (comparison) | **~210–400** |

Calculation: B0 consumption meter **CHF 0.0154 / hour** × 730 h ≈ **CHF 11.24 / month** per node; HA ≈ **CHF 22.48 / month** (two nodes).

Redis at the recommended tier is roughly **5–10× cheaper** than a single additional App Service P2v3 instance, while unlocking correct multi-instance coordination.

---

## 6. App Service settings after provision

```text
REDIS_URL=rediss://<redis-host>:6380/0
RATELIMIT_STORAGE_URI=rediss://<redis-host>:6380/0   # optional; defaults to REDIS_URL
```

Mark `REDIS_URL` as a **deployment slot setting** if staging and production use different Redis instances.

### 6.1 Application Gateway and App Service — what changes (one-time)

**In our architecture, App Service → Redis does not use Application Gateway.**

Microsoft documents two separate paths:

| Traffic | Microsoft-documented path |
|---------|---------------------------|
| **Users → web app** | Client → **Application Gateway** (Layer 7: HTTP/HTTPS/WebSocket) → App Service |
| **App Service → Redis** | App Service → **regional VNet integration** → **Private Link / private endpoint** → Redis |

Sources:

- [Application Gateway FAQ](https://learn.microsoft.com/en-us/azure/application-gateway/application-gateway-faq): Application Gateway is a **Layer 7 load balancer for web traffic** (HTTP, HTTPS, WebSocket, HTTP/2) — it fronts **inbound** client requests to your app backends.
- [App Service VNet integration](https://learn.microsoft.com/en-us/azure/app-service/overview-vnet-integration): *“Virtual network integration is used **only to make outbound calls** from your app into your virtual network.”* Outbound calls to a **private endpoint** use the integration subnet — not Application Gateway.
- [Tutorial: Isolate back-end communication](https://learn.microsoft.com/en-us/azure/app-service/tutorial-networking-isolate-vnet): App Service reaches back-end services (Key Vault, etc.) via **VNet integration + private endpoints**; *“Outbound traffic from App Service is routed to the virtual network.”*
- [Azure Managed Redis Private Link](https://learn.microsoft.com/en-us/azure/redis/private-link): Redis is reached via **private endpoint** in the VNet.
- [Azure sample: web-app-redis-sql-db](https://github.com/Azure-Samples/web-app-redis-sql-db): App Service + **Regional VNet Integration** + **Private Endpoints** to Redis and SQL — no Application Gateway in that back-end path.

> **Note:** Application Gateway v2 can also expose **TCP/TLS listeners** for some **inbound** non-HTTP workloads ([TCP/TLS proxy overview](https://learn.microsoft.com/en-us/azure/application-gateway/tcp-tls-proxy-overview)). That is an optional, explicitly configured front door — **not** the Microsoft pattern for App Service calling Redis, and **not** part of our setup. We do not configure an Application Gateway listener/backend for Redis.

| Component | Action for Redis | Ongoing? |
|-----------|------------------|----------|
| **Application Gateway** | **No change required** — Redis is not on the user→app HTTP path and we do not front Redis via AGW TCP listeners | None |
| **Application Gateway backend timeout** (e.g. ≥300s for AI/SSE) | **Unchanged** — already needed for long AI streams; unrelated to Redis | Existing setting only |
| **Private Link** (App Service VNet ↔ Redis) | **One-time** provision with Redis resource | Only if VNet layout changes later |
| **App Service `REDIS_URL`** | **One-time** app setting per slot | Only if secret rotates |
| **App Service ARR Affinity** | **One-time change after Redis verified:** set **Off** (was **On** without Redis) | Usually leave Off permanently |

**Summary for infra:** provision Redis + Private Link, set `REDIS_URL`, flip ARR Affinity Off after validation. **No Application Gateway rule updates, listeners, or backend pool changes are needed for Redis.**

After verification (`Presence store: using Redis backend` in logs):

1. Turn **ARR Affinity = Off** (staging first, then production)
2. Re-run checklist in [multi-instance without Redis](multi-instance-without-redis.md)

---

## 7. Validation checklist

- [ ] Private Link from App Service (West Europe) to Redis
- [ ] `REDIS_URL` set; no Redis errors at startup
- [ ] Presence visible across workers/instances
- [ ] Rate limits consistent regardless of instance
- [ ] Fail-open: brief Redis stop — app still serves
- [ ] ARR Affinity Off under multi-instance load

---

## 8. Ongoing maintenance (infrastructure)

**Short answer: almost nothing.** After the one-time setup in §6.1, Azure Managed Redis runs itself. Infra should not expect a recurring Redis ops workload — no backups, no patching runbooks, no manual administration.

### Day-one setup (one-time) — then done

1. Provision Azure Managed Redis B0 + Private Link  
2. Set `REDIS_URL` on App Service (per slot)  
3. Verify app logs (`Presence store: using Redis backend`)  
4. Turn **ARR Affinity Off** on App Service  
5. **Do not change Application Gateway** — not part of Redis connectivity  

After that, normal steady state is **monitor-only** (optional Azure Monitor alerts).

### What Microsoft / Azure manages (zero infra action)

| Area | Owner | Notes |
|------|--------|------|
| Redis engine & OS patching | **Azure (automatic)** | Managed service; maintenance windows may apply (standard Azure notifications) |
| High availability (prod two-node) | **Azure** | Failover handled by platform |
| Backups / point-in-time restore | **Not required for us** | All keys are **TTL-bound ephemeral coordination** — rate limits, presence, cooldowns. No business data. App **fail-open** if Redis unavailable |
| Schema / migrations | **N/A** | Plain key-value; no tables or migrations |
| Key management day-to-day | **Application (automatic)** | App creates/expiry keys via TTL; no manual key curation |

### What infrastructure typically does after go-live

**Almost nothing in routine operations.** The items below are exceptional — not monthly tasks:

| Task | Frequency | Effort |
|------|-----------|--------|
| Keep **Private Link** valid | Only if VNet / App Service networking is redesigned | Rare |
| Rotate **`REDIS_URL`** | Only if Redis rebuilt or secret policy requires it | Rare |
| Glance at **Azure Monitor** (memory %, availability) | Optional alert if you already monitor other Azure PaaS | Passive |

**Not required:** Application Gateway changes, WAF updates, new backend pools, Redis CLI sessions, backup jobs, or version upgrades.

### What the application team owns (not infra)

- Setting and verifying `REDIS_URL` after deploys
- Confirming Redis-backed behaviour in logs (`Presence store: using Redis backend`)
- Load-test / fail-open validation after major releases
- Application code changes to Redis usage (rare)

### What infra does **not** need to do

- No Redis CLI administration, manual `FLUSH`, or key inspection in normal operations
- No backup/restore runbooks for Redis (unlike PostgreSQL)
- No version upgrades of Redis software — managed by Azure
- No data migration between Redis and PostgreSQL
- No on-call Redis expertise beyond standard Azure resource health

### Comparison for reviewers worried about ops burden

| Component | Typical ongoing infra load |
|-----------|----------------------------|
| **PostgreSQL** | Backups, patching coordination, connection/capacity monitoring, migration windows |
| **App Service + Application Gateway** | Plan sizing, slot swaps, scaling rules, gateway timeouts, certificates |
| **Azure Managed Redis (our use)** | **~Zero routine tasks** after one-time Private Link + `REDIS_URL` + ARR Affinity Off |

If Redis is unavailable during an Azure maintenance window, the Backoffice **continues to serve users** (degraded per-worker coordination). Redis is **not** on the critical path for login or data persistence.

---

## 9. Related documentation

- [redis-infrastructure-request.docx](redis-infrastructure-request.docx) — infra-facing justification (Word)
- [redis-provisioning.md on GitHub](https://github.com/IFRC-C2/IFRCNetworkDatabank/blob/main/Backoffice/docs/runbooks/deployment/redis-provisioning.md)
- [Multi-instance without Redis on GitHub](https://github.com/IFRC-C2/IFRCNetworkDatabank/blob/main/Backoffice/docs/runbooks/deployment/multi-instance-without-redis.md)
- [Gateway load-test reproduction plan on GitHub](https://github.com/IFRC-C2/IFRCNetworkDatabank/blob/main/Backoffice/docs/runbooks/incidents/gateway-loadtest-reproduction-plan.md)

To refresh CHF figures locally:

```bash
python Backoffice/scripts/dev/fetch_redis_chf_price.py
```
