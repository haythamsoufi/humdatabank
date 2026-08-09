# IFRC Network Databank MCP

MCP server aligned with the [Custom GPT configuration](../Backoffice/docs/public/custom-gpt/README.md).
It proxies the **public** IFRC Humanitarian Databank API for Claude, Cursor, and other MCP clients.

**Scope:** FDRS + UPR **numeric data** and **public document** search (Unified Plans/Reports).

## Tools

| Tool | Custom GPT Action | Purpose |
|------|-------------------|---------|
| `databank_aggregate_global_trend` | `getGlobalTrend` | **Preferred** — deduped global totals by period |
| `databank_resolve_indicator` | `resolveIndicator` | Map natural-language metric names to indicator IDs |
| `databank_get_submission_coverage` | `getSubmissionCoverage` | **Preferred** — count countries with public data by template/period |
| `databank_resolve_country` | `resolveCountry` | Map a country name / ISO2/ISO3 / id to reference fields |
| `databank_search_public_documents` | `searchPublicDocuments` | Public UPR/FDRS document chunks (cited Q&A) |
| `databank_get_chunk_context` | — | Chunks immediately before/after a search result (verify/expand a truncated match) |
| `databank_get_documents_catalog` | `getPublicDocumentsCatalog` | **Preferred** — count/list public documents by type, year, country |
| `databank_get_public_document` | `getPublicDocument` | One document's metadata (title, countries, shareable link) |
| `databank_search_indicators` | `getIndicatorBank` | Search indicator bank (ranked, slim, capped) |
| `databank_get_indicator` | `getIndicatorById` | One indicator's metadata |
| `databank_get_public_data` | `getPublicData` | One page of scoped public `/data` |
| `databank_get_public_data_all_pages` | — | Auto-paginate public `/data` (raw rows; not deduped) |
| `databank_build_country_report` | — | **One-pager builder** — headline KPIs + trend + cited narrative for one country/period |
| `databank_get_report_template` | — | HTML/CSS layout skeleton + design tokens for the one-pager |
| `databank_api_info` | — | Configured base URL and endpoint summary |

Server instructions mirror [`instructions-core.md`](../Backoffice/docs/public/custom-gpt/instructions-core.md).

### Recommended flows

**FDRS trend:**
```text
databank_aggregate_global_trend(query="volunteers")
  → by_period totals (deduped, compact)
```

**UPR plan summary:**
```text
databank_search_public_documents(query="Syria unified plan 2026 focus areas")
  → chunks[] — cite document_title + page_number
```

**Cross-country UPR theme:**
```text
databank_search_public_documents(
  query="migration unified plan 2026",
  full_coverage=true
)
```

**Verify/expand a truncated or ambiguous match:**
```text
databank_get_chunk_context(chunk_id=17842, before=1, after=1)
  → neighboring chunks from the same document, in reading order
```

**Country one-pager report** ("build a report for Syria using 2026 midyear data"):
```text
databank_build_country_report(country="Syria", period_hint="2026 midyear", template_style="default")
  → country, period (resolved + available_periods), coverage, headline_kpis, trend,
    narrative (cited theme chunks), design_template (layout/colors/fonts to follow)
```
Render the JSON as an actual visual one-pager (KPI cards + trend chart + narrative bullets)
by filling `design_template.html_template` — omit `template_style` only for a freeform
render, or call `databank_get_report_template(style="default")` separately to fetch the same
layout skeleton on its own. `report_type` narrows to `"fdrs"` (numbers only) or `"upr"`
(narrative Unified Plan/Report themes only); default `"combined"` returns both. When
`coverage.fdrs_data_available` or `coverage.narrative_available` is `false`, or
`coverage.period_match_note` is set, say so explicitly instead of implying full reporting.

Neither tool ever generates or returns a PDF/HTML file — they only return data plus a
style/layout spec. Treat an inline HTML/canvas render as a quick preview; for the final
deliverable, use your own file-creation capability (e.g. Claude's `pdf` skill) to generate a
real, downloadable PDF one-pager from this JSON, following `design_template`.

**"How many countries submitted FDRS data for 2024?" (numeric):**
```text
databank_get_submission_coverage(template_id=21, period_name="Annual 2024")
  → countries_submitted_total, by_period[]
```

**"How many countries submitted an annual report / Unified Plan, all years?" (documents):**
```text
databank_get_documents_catalog(document_type="annual_report")
  → countries_count, by_year[], by_country[]
```

**Do not** sum raw `/data` rows for network-wide totals — use `databank_aggregate_global_trend`.
**Do not** paginate `/data` or `searchPublicDocuments` just to count countries — use
`databank_get_submission_coverage` / `databank_get_documents_catalog` instead.
**Do not** set `include_dimensions=true` unless explicitly needed (matches Custom GPT).

Both counting tools report **public data/document coverage only** — never internal
assignment or workflow status (submitted/pending/approved), which requires an API key.

## Report design templates

`databank_build_country_report` and `databank_get_report_template` are thin proxies over
Backoffice's `GET /public/reports/country` and `GET /public/reports/template` — all
orchestration (period resolution, KPI fetch, narrative search) and the template skeletons
themselves live server-side in `Backoffice/app/services/public/report_service.py` and
`Backoffice/app/services/public/report_styles/<style>.html` (+ `<style>.tokens.json`), shared with the
Custom GPT's `getCountryReport` / `getReportTemplate` Actions. Add a new style by dropping
files in that Backoffice folder — no MCP code changes or redeploy needed, the endpoint lists
`available_styles` from the directory contents.

## Quick start (local)

```bash
cd humanitarian-databank-mcp
pip install -r requirements.txt
python server.py
```

Uses **stdio** transport (for Cursor / Claude Desktop local config).

### HTTP mode (Claude.ai remote connector)

**PowerShell (Windows):**

```powershell
cd humanitarian-databank-mcp
$env:MCP_TRANSPORT = "streamable-http"
$env:PORT = "8000"
python server.py
```

Endpoint: `http://127.0.0.1:8000/mcp` — **not** port 5000 (Flask Backoffice).

Production: deploy `app` via `server:app` and gunicorn + uvicorn worker (see Dockerfile).

## Cursor

Wired in `.cursor/mcp.json` as `humanitarian-databank`. Restart Cursor after
`pip install -r requirements.txt`.

## Claude.ai (remote connector)

1. Deploy to a **public HTTPS URL** (e.g. `https://databank.ifrc.org/mcp` via Backoffice proxy).
2. Claude → **Settings → Connectors → Add custom connector**.
3. Paste the MCP URL → Connect → enable in chat.

Connector name: **IFRC Network Databank**. Icon:
`https://databank.ifrc.org/mcp/icon.svg` (default).

## Production deploy (Azure / Docker)

**Staging:** App Service `ifrc-databank-mcp-staging` in resource group `ifrctgo001rg`.  
**Image:** `ifrcimage.azurecr.io/databank_mcp:<tag>`  
**CI:** [`.github/workflows/deploy-mcp.yml`](../.github/workflows/deploy-mcp.yml) — manual **Run workflow** only (Actions tab).

### Backoffice proxy

```text
MCP_UPSTREAM_URL=https://ifrc-databank-mcp-staging.azurewebsites.net
```

**Env vars:**

| Variable | Default |
|----------|---------|
| `DATABANK_API_BASE` | `https://databank.ifrc.org/api/v1` |
| `MCP_PUBLIC_BASE_URL` | `https://databank.ifrc.org` (connector icon URL base) |
| `PORT` | `8000` |
| `MCP_MAX_CONCURRENT_DOCUMENT_SEARCHES` | `1` — serializes `databank_search_public_documents` calls so parallel tool calls don't stack concurrent load on the upstream search endpoint |
| `DATABANK_DOCUMENT_SEARCH_MAX_RETRIES` | `1` — retries once on a transient 5xx (statement-timeout 503, gateway 502/504) |
| `DATABANK_DOCUMENT_SEARCH_RETRY_DELAY_SECONDS` | `2.0` — delay before that retry |

## Tests

```bash
pip install -r requirements.txt
python -m pytest tests/ -q
```
