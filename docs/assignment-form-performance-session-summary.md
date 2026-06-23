# Assignment Form Performance — Session Summary

High-level record of performance and static-asset work on the IFRC Humanitarian Databank Backoffice (`databank.ifrc.org`), focused on assignment entry forms (504s, slow loads, static CDN, and ES module caching).

---

## Goals

- Diagnose and fix production slowness on assignment forms (504 timeouts, ~34s page loads).
- Offload static assets from Gunicorn workers to Azure Blob Storage / CDN.
- Eliminate duplicate JS fetches caused by versioned entry scripts vs unversioned ES module imports.
- Validate improvements with HAR captures before and after changes.

---

## Server-Side Optimizations

| Change | Location | Purpose |
|--------|----------|---------|
| **Flask-Compress** (Brotli + gzip, `COMPRESS_STREAMS=True`) | `Backoffice/app/__init__.py` | Smaller HTML/API payloads on the wire |
| **Jinja trim/lstrip blocks** | `Backoffice/app/__init__.py` | Smaller rendered HTML |
| **`stream_template` for assignment forms** | `Backoffice/app/routes/forms/entry.py` | Start sending HTML sooner; works with transaction middleware streaming |
| **Prior session work** (referenced) | CSRF API refresh, N+1 query fixes, template cache, SW bypass for assignment HTML, lazy JS modules, chatbot deferral on entry forms | Reduced server work and client payload |

**Observed impact (prod HAR):** onLoad dropped from ~34s to ~2.8s; HTML TTFB ~2.1s (down from ~3.5s); compressed HTML ~84 KB wire; no static 504s.

---

## Static CDN (Azure Blob)

### Application code

- **`static_url()` CDN support** — `Backoffice/app/template_context.py`: when `STATIC_CDN_URL` is set, assets use `{cdn}/{path}?v={ASSET_VERSION}` instead of Flask `/static/`.
- **CSP updates** — `Backoffice/app/middleware/security_headers.py`: allow blob CDN origin in `script-src`, `style-src`, `font-src`, `connect-src`.
- **Cache headers** — `Backoffice/app/static_serving.py`: versioned assets get `Cache-Control: max-age=31536000, public, immutable`; fixed `Headers.remove` (was `.discard`, caused crashes).

### Infrastructure

- Storage account: **`ifrcdatabankstorage2`**
- Containers: **`static`** (production), **`static-staging`** (staging)
- Public blob read + CORS for `databank.ifrc.org` and Azure Web App URLs
- ~467 static files uploaded to both containers

### CI/CD

- **`Backoffice/azure/upload-static-assets.sh`** — AzCopy sync (incremental), parallel `Cache-Control` metadata pass after sync
- **`.github/workflows/deploy-to-webapp.yml`** — uploads static assets on deploy; container chosen by environment
- Requires GitHub secret **`AZURE_STORAGE_CONNECTION_STRING`**

### Manual app settings (Azure Portal)

- Production: `STATIC_CDN_URL=https://ifrcdatabankstorage2.blob.core.windows.net/static`
- Staging: `STATIC_CDN_URL=https://ifrcdatabankstorage2.blob.core.windows.net/static-staging`

---

## Duplicate Unversioned ES Module Imports

### Problem

Top-level scripts used `static_url()` → `entry-form.js?v=…` on blob, but relative imports (`import './main.js'`) resolved to the same blob path **without** `?v=`. Browsers treated these as separate cache keys → duplicate fetches (e.g. `main.js`, `debug.js`, `presence.js` loaded twice). Layout also loaded `debug.js` versioned while `main.js` imported it unversioned.

### Solution

1. **`Backoffice/app/static_import_map.py`** — Scans `js/forms/` for relative `import` / `import()` specifiers (`./` and `../`), builds a **scoped import map** mapping each to the same versioned URL as `static_url()`.
2. **`entry_form.html`** — Injects `<script type="importmap">` in `{% block head %}` **before** layout module scripts.
3. **`layout.html`** — `window.getStaticUrl()` uses `STATIC_CDN_URL` when set (mirrors server-side `static_url()`).
4. **`template_context.py`** — Jinja globals: `forms_module_import_map()`, `STATIC_CDN_URL`.

### Bug fix (template crash)

Entry form routes pass `config=Config` (the **class**), which shadowed the Jinja global `config` (`app.config`). `layout.html` called `config.get('STATIC_CDN_URL')` and crashed. Fixed by exposing **`STATIC_CDN_URL`** as its own global (same pattern as `ASSET_VERSION`).

### Tests

- `Backoffice/tests/unit/test_static_import_map.py` — 3 tests, all passing.

---

## HAR Analysis (`databank.ifrc.org.har`)

### Tools

- `scripts/analyze_har.py` — general performance review
- `scripts/analyze_har_cache.py`, `scripts/analyze_har_network_js.py` — per-reload cache breakdown (added during session)

### Findings (3 reloads)

| Metric | Result |
|--------|--------|
| **JS cache** | Reloads 2–3: **0 B** transferred for all form JS; reload 1: only **4 KB** (`sw.js`) from network |
| **CDN** | ~65 JS requests per reload from blob; immutable cache headers correct |
| **Still on network each reload** | HTML ~84 KB (dynamic, expected); APIs ~35–37 KB (presence, completion-rate, dynamic indicators, etc.) |
| **Pre–import-map deploy** | No `<script type="importmap">` in HTML; 30 versioned + 35 unversioned blob URLs per reload; `debug.js` duplicated (versioned + unversioned) |
| **WebSocket** | `wss://…/api/notifications/ws` “Pending” in DevTools is normal (long-lived connection, not connect delay) |

**Note:** DevTools still **lists** ~65 JS requests per reload when served from disk cache — use **Transferred = 0 B** or **(disk cache)** in the Size column to verify caching.

---

## Rollout Checklist

1. Deploy Backoffice code (import map + `STATIC_CDN_URL` global + compress/stream changes).
2. Confirm `STATIC_CDN_URL` in Azure App Settings for prod/staging.
3. Ensure CI static upload runs (or run `upload-static-assets.sh` manually).
4. Hard-refresh assignment form; **View Source** → confirm `<script type="importmap">` present.
5. Capture new HAR: expect single URL per module (all with `?v=`), 0 B JS wire on reload 2+.

---

## Out of Scope / Not Done

- Page-scoped Jinja rendering (options 1 and 5 from earlier discussion — user declined).
- Bundler/build step for form JS (import map chosen to avoid rewriting every import).
- Service worker precache alignment with blob CDN (separate follow-up if needed).

---

## Key Files Touched

```
Backoffice/app/__init__.py
Backoffice/app/template_context.py
Backoffice/app/static_import_map.py
Backoffice/app/static_serving.py
Backoffice/app/middleware/security_headers.py
Backoffice/app/routes/forms/entry.py
Backoffice/app/templates/core/layout.html
Backoffice/app/templates/forms/entry_form/entry_form.html
Backoffice/config/config.py
Backoffice/env.example
Backoffice/azure/upload-static-assets.sh
.github/workflows/deploy-to-webapp.yml
Backoffice/tests/unit/test_static_import_map.py
scripts/analyze_har.py
scripts/analyze_har_cache.py
scripts/analyze_har_network_js.py
```
