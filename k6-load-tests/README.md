# Backoffice load tests (k6)

Self-contained [k6](https://k6.io/) load-testing suite for the **Flask Backoffice** application
(`Backoffice/`). All scripts, helpers, and docs live under this `k6-load-tests/` directory only —
nothing is added under `Backoffice/`, `Website/`, or `MobileApp/`.

> **Staging only.** These scripts are designed for staging or local environments.
> Do **not** run them against production without explicit ops sign-off.

---

## Requirements

- [k6](https://grafana.com/docs/k6/latest/set-up/install-k6/) (single binary; not a Python/Node package).
- Network access to a Backoffice origin (local dev server, staging, etc.).

Verify k6 is installed:

```bash
k6 version
```

---

## Phases

| Phase | Scope | Status |
|------|-------|--------|
| **1** | Smoke (`/health`, `/api/ai/v2/health`) + 1–2 `/api/v1` reads with API key. | Implemented |
| **1.5** | Broader Backoffice coverage: extended `/api/v1` reads, document downloads, opt-in AI chat smoke, opt-in write smoke, mixed realistic profile. | Implemented (opt-in gates) |
| **2** | Website (Next.js) + Mobile API (`/api/mobile/v1`) scenarios. | Roadmap (not implemented) |

See **Roadmap** at the bottom of this file.

---

## Environment variables

See [`./env.example.txt`](./env.example.txt) for the full list of variable names.
Variables can be passed to k6 via `-e KEY=VALUE` on the command line or via the
shell environment. (We use `env.example.txt` rather than `.env.example` so the
file is never accidentally interpreted as a real `.env` file.)

### Phase 1 (always available)

| Variable | Default | Purpose |
|----------|---------|---------|
| `BASE_URL` | `http://127.0.0.1:5000` | Backoffice origin (e.g. staging URL). **Backoffice only**, not the public Website. |
| `K6_BACKOFFICE_API_KEY` | _(unset)_ | Bearer token for `/api/v1` GET scenarios. Create a dedicated read-only key in staging. |
| `K6_PROFILE` | _(auto)_ | Threshold profile: `local` (relaxed, tolerates Werkzeug dev server) or `staging` (strict, assumes warm gunicorn). Auto-detected from `BASE_URL` when unset (loopback hosts → `local`, anything else → `staging`). |

### Phase 1.5 (opt-in scenarios)

| Variable | Default | Purpose |
|----------|---------|---------|
| `K6_DOC_IDS` | _(unset)_ | Comma-separated submitted-document IDs for `document-download.js` (e.g. `12,34,56`). Optional. |
| `K6_RESOURCE_IDS` | _(unset)_ | Comma-separated `id:lang` pairs for resource downloads (e.g. `7:en,9:fr`). Optional. |
| `K6_AI_TOKEN` | _(unset)_ | Preissued AI Bearer JWT (`GET /api/ai/v2/token` while logged in). Required by `ai-chat-smoke.js` when enabled. |
| `K6_AI_CHAT_ENABLED` | `false` | Set to `true` to actually run the AI chat scenario. Otherwise the script is a no-op (cost guard). |
| `K6_WRITE_ENABLED` | `false` | Set to `true` to actually run the write-smoke scenario. **Throwaway staging DB only.** |
| `K6_WRITE_PATH` | `/api/v1/indicator-suggestions` | Endpoint used by `write-smoke.js` when enabled. |

> **Auth note:** API keys must be sent in the `Authorization: Bearer <key>` header.
> Query-string keys are explicitly rejected by `Backoffice/app/utils/auth.py:_extract_api_key()`.

---

## Running the scripts

All commands assume your shell is at the **repository root**.

### Phase 1

```bash
# Smoke: GET /health and GET /api/ai/v2/health
k6 run k6-load-tests/scenarios/smoke-backoffice.js -e BASE_URL=https://your-staging-host

# /api/v1 reads (1–2 endpoints) — requires Bearer API key
k6 run k6-load-tests/scenarios/api-v1-reads.js \
  -e BASE_URL=https://your-staging-host \
  -e K6_BACKOFFICE_API_KEY=your_staging_key
```

### Phase 1.5

```bash
# Extended /api/v1 read coverage (non-rate-limited GETs)
k6 run k6-load-tests/scenarios/api-v1-reads-extended.js \
  -e BASE_URL=https://your-staging-host \
  -e K6_BACKOFFICE_API_KEY=your_staging_key

# Public document / thumbnail downloads (needs known staging IDs)
k6 run k6-load-tests/scenarios/document-download.js \
  -e BASE_URL=https://your-staging-host \
  -e K6_DOC_IDS=12,34,56 \
  -e K6_RESOURCE_IDS=7:en,9:fr

# Mixed realistic profile (health + reads + optional documents)
k6 run k6-load-tests/scenarios/mixed-realistic.js \
  -e BASE_URL=https://your-staging-host \
  -e K6_BACKOFFICE_API_KEY=your_staging_key

# AI chat smoke — DISABLED by default; opt-in only (LLM cost!)
k6 run k6-load-tests/scenarios/ai-chat-smoke.js \
  -e BASE_URL=https://your-staging-host \
  -e K6_AI_TOKEN=eyJ... \
  -e K6_AI_CHAT_ENABLED=true

# Write smoke — DISABLED by default; throwaway staging DB only
k6 run k6-load-tests/scenarios/write-smoke.js \
  -e BASE_URL=https://your-staging-host \
  -e K6_BACKOFFICE_API_KEY=your_staging_key \
  -e K6_WRITE_ENABLED=true
```

---

## Safety & policy

- **Default profile is small:** short duration, low VUs (typically 1–10).
- **Opt-in scenarios** (AI chat, writes) **no-op** unless their gate variable is `true`.
- **Rate limits:** scripts target endpoints flagged `rate_limited: False` in
  `Backoffice/app/routes/admin/api_management.py`. If you change scripts to hit
  rate-limited endpoints, expect HTTP `429` and tune VUs/RPS down accordingly.
- **AI health (`/api/ai/v2/health`)** can return `503` if `OPENAI_API_KEY` (or related
  config) is not present in the target environment. Treat that as an environment
  signal, **not** a k6 bug.
- **Do not** point unbounded load at production without ops sign-off.

### Default thresholds (starting points, not SLOs)

`k6-load-tests/lib/config.js` defines two threshold profiles. Each script uses the active
profile via the helper functions (`defaultThresholds()`, `healthThresholds()`,
`aiHealthThresholds()`, `profileValues()`).

| Metric | `local` profile | `staging` profile |
|--------|-----------------|-------------------|
| `http_req_failed` rate | < 5% | < 1% |
| `health` p(95) / p(99) | 2 s / 5 s | 300 ms / 800 ms |
| `ai-health` p(95) / p(99) | 5 s / 10 s | 2 s / 5 s |
| default `http_req_duration` p(95) / p(99) | 5 s / 10 s | 1.5 s / 3 s |
| heavy reads (e.g. `data/tables`) p(95) | 8 s | 3 s |
| document download p(95) / p(99) | 8 s / 20 s | 3 s / 8 s |
| AI chat p(95) | 60 s | 30 s |

Override per environment by setting `K6_PROFILE=local` or `K6_PROFILE=staging`.
When `K6_PROFILE` is unset the profile is auto-detected from `BASE_URL`
(loopback host → `local`, otherwise `staging`).

### Cold-start warmup

Each measured scenario runs a short warmup in `setup()` before VUs spin up:
one request per measured endpoint. k6 does **not** count `setup()` requests
toward the threshold metrics, so the first lazy-load hit (DB pool open, AI
integration init, ORM mappers) is excluded from p(95)/p(99).

---

## Continuous Integration

A manual workflow lives at
[`.github/workflows/k6-load-test.yml`](../.github/workflows/k6-load-test.yml).

- Trigger: **`workflow_dispatch` only** (never on PR push).
- Inputs: `scenario` (which script to run) + `base_url`.
- Secrets: `K6_BACKOFFICE_API_KEY`, `K6_AI_TOKEN`, `K6_DOC_IDS`, `K6_RESOURCE_IDS` —
  configured per **GitHub Environment** (e.g. `staging`).

The workflow only runs scripts under `k6-load-tests/`; it does **not** invoke any Python tests
or build steps from `Backoffice/`.

---

## Roadmap (Phase 2)

These are **not** implemented yet. Placeholder folders are intentionally absent so
no empty directories appear in the tree.

### Website (Next.js)

- Path: `k6-load-tests/scenarios/website/` (to be created).
- Targets the **public Website base URL** (separate origin from Backoffice).
- Scenarios: `GET /` and a few public routes the site actually calls.
- Caveats: CDN caching, ISR/SSG vs SSR, rate limits on any API the site proxies.

### Mobile API (`/api/mobile/v1`)

- Path: `k6-load-tests/scenarios/mobile/` (to be created).
- Hits the Backoffice mobile blueprint — **not** the Flutter binary.
- Auth: preissued JWT in env (never per-VU storm on `POST /api/mobile/v1/auth/token`,
  which is wrapped with `@auth_rate_limit()`).
- Headers: `X-App-Version` configurable vs `MOBILE_MIN_APP_VERSION`.

---

## File structure

```
k6-load-tests/
├── README.md                 (this file)
├── env.example.txt           (variable names only, no values)
├── lib/
│   ├── config.js             (BASE_URL, headers, default thresholds)
│   └── checks.js             (shared response checks)
└── scenarios/
    ├── smoke-backoffice.js           # Phase 1
    ├── api-v1-reads.js               # Phase 1
    ├── api-v1-reads-extended.js      # Phase 1.5
    ├── document-download.js          # Phase 1.5
    ├── ai-chat-smoke.js              # Phase 1.5 (opt-in)
    ├── write-smoke.js                # Phase 1.5 (opt-in)
    └── mixed-realistic.js            # Phase 1.5
```
