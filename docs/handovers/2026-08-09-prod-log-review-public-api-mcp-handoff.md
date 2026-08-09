# Prod log review — public API / MCP performance & bugs (2026-08-09)

**Status:** Open — agent handoff  
**Environment:** Production (`ifrc-databank-app`, RG `ifrcpunifiedplanning-rg001`, West Europe)  
**Investigation window:** **00:00–22:03 CEST** (full calendar day, partial — logs downloaded ~22:07 CEST)  
**Investigator:** prod log review session (2026-08-09 evening)  
**Audience:** Agent already working on public API / MCP / vector-search bug fixes  
**Related playbooks:** [Gateway 504 / worker saturation](../../Backoffice/docs/runbooks/incidents/gateway-504-worker-saturation.md), [2026-07-16 prod 504 findings](../../Backoffice/docs/runbooks/incidents/2026-07-16-prod-gateway-504-findings.md), [Logging & health](../../Backoffice/docs/runbooks/observability/logging-and-health.md)

---

## 1. Executive summary

Production was **mostly healthy for normal browser users** today (form work, CSRF refreshes, scheduled digests). The actionable noise is concentrated on:

1. **`GET /api/v1/public/documents/search`** — hybrid/vector queries ran **18–374 seconds**, tripped Postgres **`statement_timeout` (~18 s)** → HTTP **503**, and produced **32 `[STUCK_REQUEST]`** alerts. Traffic was predominantly **`python-httpx/0.28.1`** (MCP / Custom GPT Actions / automation), including `TESTQUERY_ONE`…`FIVE` and broad `full_coverage=true` searches.
2. **`GET /api/v1/indicator-bank?search=appeal&emergency=true`** → HTTP **500** — confirmed SQL bug: **`ILIKE` on boolean `emergency` column**.
3. **AI bulk reprocess** — 7× Word processing failures, 2× oversize files (54.2 MB > 50 MB cap), **1× WORKER TIMEOUT** during PDF processing, **1× platform 504** on reprocess status polling.

**Overlap with your recent work:** commits `c559891e` (batched `hybrid_search_per_document`, catalog blob-check fix) and `ce3b9d9b` (public document service + MCP expansion) target the same surface area. Uncommitted MCP changes in `humanitarian-databank-mcp/server.py` (document-search semaphore, response echo verification, 5xx retry) directly address finding #1 — **verify whether those fixes are deployed to prod MCP before closing this handoff**.

---

## 2. Log archive & how to re-fetch

### Local archive (from this review)

| Path | Contents |
|------|----------|
| `Backoffice/instance/logs/prod-20260809/prod-logs.zip` | Raw Azure download |
| `Backoffice/instance/logs/prod-20260809/extracted/LogFiles/` | Extracted tree |
| `Backoffice/instance/logs/prod-20260809/extracted/LogFiles/2026_08_09_*_default_docker.log` | **App stdout** (4 files, ~1 MB total, ~5351 lines) |

> Note: `Backoffice/instance/logs/` may be `.cursorignore`d — use shell/`rg` for analysis.

### Re-fetch command

```powershell
az account set --subscription "3e33b4c1-ada7-4922-9113-b9e41eaf1797"
az webapp log download `
  --name ifrc-databank-app `
  --resource-group ifrcpunifiedplanning-rg001 `
  --log-file "Backoffice/instance/logs/prod-YYYYMMDD/prod-logs.zip"
```

Or via repo helper: `azure_webapp_tools.bat prod logs` (live tail only — use `az webapp log download` for historical search).

### Quick grep patterns (run against `*_default_docker.log`)

```powershell
$logs = Get-ChildItem "Backoffice/instance/logs/prod-20260809/extracted/LogFiles" -Filter "*2026_08_09*default_docker.log"
$all = $logs | ForEach-Object { Get-Content $_.FullName -Encoding UTF8 }

# Counts
$all | Select-String 'STUCK_REQUEST|WORKER TIMEOUT|OperationalError|indicator.bank|Bulk reprocess| 503 | 500 '
```

---

## 3. Key metrics (2026-08-09)

| Metric | Value |
|--------|------:|
| Total app log lines | ~5,351 |
| `[STUCK_REQUEST]` / `_CRITICAL` | 32 |
| `[SLOW_REQUEST]` (>10 s) | 18 |
| `ERROR` (incl. stuck-as-error) | 76 |
| `Traceback` blocks | 30 |
| `WORKER TIMEOUT` | 1 |
| Platform **504** (real gateway) | 1 |
| HTTP **503** on public search | 3 |
| HTTP **500** | 1 (indicator bank) |
| `QueryCanceled` / `statement_timeout` | 5 |
| Bulk reprocess item failures | 9 |
| RBAC unguarded-route warnings | 17 (`/admin/reports/*`) |
| CSRF errors | 0 (12 successful token refreshes) |
| Migration / OpenAI provider errors | 0 |

---

## 4. Timeline (CEST)

| Time | Event |
|------|-------|
| **02:01** | Container restart + deploy (migrations OK, head `report_definition_v2_schema`) |
| **02:01–02:03** | Bulk reprocess job `a1fec334-b833-4bcd-8d7b-aafcdf6e8f5e` — Word errors (1140, 1142), oversize (1148) |
| **02:02:48** | **`WORKER TIMEOUT` pid 78** while processing `Annual Report_Armenia_2023.pdf` (7.8 MB) during reprocess → `SIGKILL! Perhaps out of memory?` |
| **02:17, 04:01, 04:14** | Additional container restarts (deploys) |
| **08:00** | FDS access-request digest: `sent=0, failed=0` |
| **12:05–12:12** | Post Office partnership public-search queries → HTTP **400** (invalid `country_ids` combos) |
| **12:11** | `GET /api/v1/public/documents/catalog?include_documents=true` stuck 23 s → completed in **31.8 s** |
| **18:28** | Bulk reprocess job `980a29f8-3ebb-4f8f-884d-179b7b5d3932` — burst of Word errors (1150–1154), oversize (1149) |
| **18:28:20** | **Platform 504** on `/admin/ai/documents/bulk-reprocess/1710b082-…/status` (67 req/min on reporter worker, 0 in-flight) |
| **18:35, 19:56** | Container restarts |
| **21:14–22:03** | **MCP/automation public-search burst** (`python-httpx`) — stuck requests, 3×503, searches up to **374 s** |
| **21:15:01** | **`GET /api/v1/indicator-bank?search=appeal&emergency=true` → 500** |

---

## 5. Findings (detailed)

### 5.1 P1 — Public document search slow / 503 / worker pressure

**Endpoint:** `GET /api/v1/public/documents/search`  
**Client:** `python-httpx/0.28.1` (MCP server, Custom GPT Actions, or direct httpx scripts)  
**User-Agent on some calls:** `-` (no browser UA)

**Evidence (sample log lines):**

```
[STUCK_REQUEST_CRITICAL] … path=/api/v1/public/documents/search … after 23.0s
[SLOW_REQUEST] Completed in 374.02s … query=emergency+appeal&full_coverage=true
[SLOW_REQUEST] Completed in 349.62s … query=blood+donation+campaign&full_coverage=true
ERROR … Vector search with embedding failed: QueryCanceled … statement timeout
GET …/public/documents/search?query=blood… HTTP/1.1" 503 144 "-" "python-httpx/0.28.1" 18634188
```

**503 response body:** 144 bytes — maps to `PublicDocumentSearchUnavailable` in Backoffice.

**Root cause chain (from logs + code):**

1. Broad / `full_coverage=true` hybrid search fans out across many public documents.
2. Vector similarity queries hit Postgres **`statement_timeout`** (~18 s per comments in `document_service.py`).
3. Gunicorn worker stuck-request monitor fires at 15 s / 23 s while query still runs.
4. Some requests complete after **minutes**; others return **503** when timeout wins.
5. Concurrent httpx calls from one MCP client landed on the **same worker** and contended for DB pool (same failure mode as July 504 incidents, but on public search not notification polling).

**Code pointers:**

| File | Relevance |
|------|-----------|
| `Backoffice/app/services/public/document_service.py` | Public search orchestration, `full_coverage`, `PUBLIC_DOC_SCOPED_SEARCH_MAX_DOCS`, 503 mapping |
| `Backoffice/app/services/ai/documents/vector_store.py` | `hybrid_search_per_document`, `_search_similar_with_embedding` — where tracebacks point |
| `Backoffice/app/routes/api/public_integrations.py` | Route handler, `full_coverage` param parsing |
| `Backoffice/docs/public/custom-gpt/instructions-core.md` | Instructs GPT to use `full_coverage=true` for cross-country themes |

**Recent fixes (may not be on prod yet — verify deploy):**

| Commit | What it did |
|--------|-------------|
| `c559891e` | Batched `hybrid_search_per_document` (2 queries total vs 2×N); catalog blob HEAD skip; `joinedload(AIDocument.country)` |
| `ce3b9d9b` | Large public document service expansion + MCP tool additions + tests |

**In-flight (uncommitted at handoff time):**

| File | Change |
|------|--------|
| `humanitarian-databank-mcp/server.py` | `_DOCUMENT_SEARCH_SEMAPHORE` (default 1 concurrent upstream search); `(Exception, asyncio.CancelledError)` handling; investigation notes cite this incident |
| `humanitarian-databank-mcp/databank_client.py` | Echoed `query` field verification; retry on 500/502/503/504 |
| `humanitarian-databank-mcp/tests/test_server_document_search_concurrency.py` | Semaphore serialization tests (new, untracked) |

**Still open on Backoffice side (even after batch fix):**

- `full_coverage=true` with `top_k=8` and `per_page=80` still produced **374 s** and **349 s** completions — batching alone may not be enough.
- Consider: hard wall-clock cap below AGW ~30 s, stricter rate limit on unauthenticated search, lower default `per_page`, or moving heavy search off sync gunicorn workers.
- `Batched hybrid_search_per_document failed, falling back to per-document loop` appeared **2×** in warnings — investigate why batch path failed.

**Suggested verification after deploy:**

```bash
# From MCP or curl — should not 503 under normal load
curl -sS "https://databank.ifrc.org/api/v1/public/documents/search?query=health&full_coverage=false&top_k=3"
# Known slow path — time it
curl -sS "https://databank.ifrc.org/api/v1/public/documents/search?query=emergency+appeal&full_coverage=true&top_k=8&per_page=80"
```

---

### 5.2 P1 — Indicator bank `emergency=true` → HTTP 500 (confirmed bug)

**Request:** `GET /api/v1/indicator-bank?search=appeal&emergency=true`  
**Time:** 21:15:01 CEST  
**Client:** `python-httpx/0.28.1`

**SQL error:**

```
psycopg2.errors.UndefinedFunction: operator does not exist: boolean ~~* unknown
LINE 3: ... AND indicator_bank.emergency ILIKE '%true%'
```

**Root cause:** `indicators.py` passes `emergency` as a **string** query param; `bank_service.py` applies `.ilike()` on a **boolean** column:

```415:418:Backoffice/app/services/indicators/bank_service.py
    if filters.emergency:
        query = query.filter(
            IndicatorBank.emergency.ilike(safe_ilike_pattern(filters.emergency))
        )
```

**MCP surface:** `databank_search_indicators(emergency="")` in `humanitarian-databank-mcp/server.py` forwards the string verbatim — LLM passing `emergency=true` triggers this.

**Fix (straightforward):** Parse `emergency` as bool (`true`/`false`/`1`/`0`) and filter with `IndicatorBank.emergency.is_(True/False)`. Add unit test in indicator bank service tests.

**Status:** Not fixed in prod as of log window.

---

### 5.3 P2 — AI bulk reprocess failures

**Jobs observed:**

| Job ID | Window (CEST) | Notes |
|--------|---------------|-------|
| `a1fec334-b833-4bcd-8d7b-aafcdf6e8f5e` | ~02:00–02:03 | Early-morning reprocess during deploy |
| `980a29f8-3ebb-4f8f-884d-179b7b5d3932` | ~20:28 | Word error burst |
| `1710b082-51be-45b5-bf2d-48de2f141ba5` | ~20:28 | Status poll got 504 |

**Failed items:**

| Item ID | Error |
|---------|-------|
| 1140, 1142 | `Word processing error.` |
| 1150, 1151, 1152, 1153, 1154 | `Word processing error.` |
| 1148, 1149 | `File too large: 54.2MB (max: 50.0MB)` |

**Code pointers:** `app/routes/admin/ai_management.py` (`_process_reprocess_job_item_sync`), `app/services/ai/documents/processor.py` (`DocumentProcessingError`).

**Follow-up:** Inspect source files for items 1140, 1142, 1150–1154 in admin AI documents UI / blob storage. Decide policy for >50 MB public docs.

---

### 5.4 P2 — Worker timeout during PDF reprocess (02:02 CEST)

```
[CRITICAL] WORKER TIMEOUT (pid:78)
[ERROR] Worker (pid:78) was sent SIGKILL! Perhaps out of memory?
```

**Context:** Worker was processing bulk reprocess — had just finished doc 640 (10 MB PDF, 209 embeddings) and started doc 639 (`Annual Report_Armenia_2023.pdf`, 7.8 MB) when gunicorn's **25 s worker timeout** fired.

**Risk:** Synchronous document processing on gunicorn workers blocks the same pool serving API traffic. Same class of problem as July worker-saturation incidents.

**Follow-up:** Confirm reprocess runs on background threads (`AI job thread started` appears in logs) but PDF parse/embed may still block the worker that accepted the status-poll connection. Consider isolating heavy processing from web workers entirely.

---

### 5.5 P2 — Platform 504 on bulk-reprocess status poll (20:28 CEST)

```
CRITICAL … platform_504_gateway_timeout … /admin/ai/documents/bulk-reprocess/1710b082-…/status
likely: Elevated request rate on this worker … traffic 67/min … DB pool 1/10 … reporter worker pid=4656: 0 in-flight
```

Classic **canary** pattern — status endpoint is not root cause; worker was busy with reprocess + admin UI polling. See [gateway-504 runbook](../../Backoffice/docs/runbooks/incidents/gateway-504-worker-saturation.md).

---

### 5.6 P3 — RBAC startup warning (`/admin/reports/*`)

Every worker boot:

```
RBAC: detected 17 /admin route(s) without an RBAC guard decorator … /admin/reports/*
```

**Likely false positive:** `Backoffice/app/routes/admin/reports/routes.py` uses manual `_forbidden_if_no_view()` / `permission_required` instead of the scanner's expected decorators. **Agent working on reports** (`routes.py` modified in current branch) should confirm all 17 routes call permission checks.

---

### 5.7 Low / informational

| Signal | Notes |
|--------|-------|
| **429 rate limit** | 4× `POST /admin/ai/documents/{106,109,112,113}/delete` at 02:01 — limiter working |
| **400 public search** | Post Office `country_ids` validation failures (12:05–12:12) — may relate to `ce3b9d9b` multi-country batching work |
| **CSRF** | All 200 — no issues |
| **Scheduler lock reclaim** | During deploy restarts — expected without `REDIS_URL` |
| **404** | `robots.txt`, `/.well-known/assetlinks.json` — bots |
| **Container restarts** | ~6 full restarts today — correlate with deploy pipeline |

---

## 6. Mapping to your branch / recent commits

If you've been on the "Bug fix" series, this table links log findings to likely touch points:

| Finding | Likely files you've touched | Commit hints |
|---------|----------------------------|--------------|
| Public search 503/timeout | `document_service.py`, `vector_store.py`, `public_integrations.py`, MCP `server.py` | `c559891e`, `ce3b9d9b`, uncommitted MCP semaphore |
| Catalog slow (31 s) | Same + blob HEAD skip | `c559891e` |
| Indicator bank 500 | `bank_service.py`, `indicators.py`, MCP `search_indicators_ranked` | **Not in recent commits — open** |
| Post Office 400 | `document_service.py` country_ids batching | `ce3b9d9b` |
| Reports RBAC warning | `admin/reports/routes.py` | Current uncommitted changes |
| Keyword boost scoring | `vector_store.py` `_combine_search_results` | `test_vector_store_combine.py` in git status (prior session) |

**Check what's actually deployed to prod:**

```powershell
# Latest prod container image / slot — compare to local HEAD
az webapp show --name ifrc-databank-app --resource-group ifrcpunifiedplanning-rg001 --query "siteConfig.linuxFxVersion"
```

MCP is deployed separately (`.github/workflows/deploy-mcp.yml`) — prod MCP may lag Backoffice.

---

## 7. Recommended actions (priority)

| P | Action | Owner hint |
|---|--------|------------|
| **P0** | Fix `emergency` boolean filter in `bank_service.py` + test | Backoffice API |
| **P0** | Deploy MCP semaphore + retry + echo verification if not live | MCP (`server.py`, `databank_client.py`) |
| **P1** | Confirm `c559891e` batch path is on prod; investigate 2× batch fallback warnings | Backoffice |
| **P1** | Add wall-clock timeout / rate limit on public search; cap `full_coverage` cost | Backoffice |
| **P2** | Triage Word doc failures (1140, 1142, 1150–1154) | AI documents admin |
| **P2** | Review bulk reprocess isolation from gunicorn workers | AI pipeline |
| **P3** | Confirm `/admin/reports` manual RBAC on all 17 routes | Reports agent |

---

## 8. Test plan (post-fix)

- [ ] `GET /api/v1/indicator-bank?search=appeal&emergency=true` → **200**, filtered results
- [ ] `GET /api/v1/public/documents/search?query=health&top_k=3` → **200** in <10 s
- [ ] `full_coverage=true` cross-country query → completes or fails fast with clear error (not 6 min)
- [ ] MCP: fire 5 parallel `databank_search_public_documents` → max 1 upstream concurrent (default)
- [ ] MCP: simulated 503 → single retry then clear error string
- [ ] Bulk reprocess a known-good small PDF → no worker timeout on status poll
- [ ] Worker boot → no new ERROR/CRITICAL in first 2 minutes (smoke checklist from azure-app-service runbook)

---

## 9. Related docs & code

- [Custom GPT instructions (full_coverage guidance)](../../Backoffice/docs/public/custom-gpt/instructions-core.md)
- [Azure App Service deploy & log streaming](../../Backoffice/docs/runbooks/deployment/azure-app-service.md)
- [MCP README](../../humanitarian-databank-mcp/README.md)
- [Developer handbook — public API section](../../docs/DEVELOPER-HANDBOOK.md)

---

*Handoff created 2026-08-09. Update this doc when fixes ship or prod is re-checked.*
