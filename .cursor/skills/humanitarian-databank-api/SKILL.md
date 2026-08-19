---
name: humanitarian-databank-api
description: >-
  Paste-first IFRC Databank analysis. Give user curl commands immediately; parse
  pasted JSON. Public /api/v1 only. Never live-fetch databank.ifrc.org.
---

# Humanitarian Databank — Public API

**Base URL:** `https://databank.ifrc.org/api/v1`

**Mode:** User runs curl (or browser) → pastes JSON → you analyze.  
**Or:** use the **IFRC Network Databank** MCP connector when enabled (live fetch).  
Full schemas: [reference.md](reference.md). Custom GPT parity: [`Backoffice/docs/public/custom-gpt/`](../../Backoffice/docs/public/custom-gpt/README.md).

---

## MCP connector (preferred when available)

If the **humanitarian-databank** / **IFRC Network Databank** MCP tools are connected,
call them directly — do not curl or web_fetch:

| Tool | Custom GPT | Use for |
|------|------------|---------|
| `databank_aggregate_global_trend` | `getGlobalTrend` | **Global totals by year** (deduped; preferred) |
| `databank_resolve_indicator` | `resolveIndicator` | Map "volunteers" / "staff" → indicator id |
| `databank_get_submission_coverage` | `getSubmissionCoverage` | **Count countries with public data** by template/period (preferred) |
| `databank_resolve_country` | `resolveCountry` | Map a country name/ISO code/id → id, iso2, iso3, region |
| `databank_search_public_documents` | `searchPublicDocuments` | **UPR/FDRS public document chunks** (cite title + page) |
| `databank_get_documents_catalog` | `getPublicDocumentsCatalog` | **Count/list public documents** by type, year, country (preferred) |
| `databank_get_public_document` | `getPublicDocument` | One document's metadata (title, countries, shareable link) |
| `databank_search_indicators` | `getIndicatorBank` | Find indicator ids by keyword (ranked, capped) |
| `databank_get_indicator` | `getIndicatorById` | Full metadata for one id |
| `databank_get_public_data` | `getPublicData` | One page of scoped public data (raw rows) |
| `databank_get_public_data_all_pages` | — | Raw multi-page export (not deduped) |
| `databank_build_country_report` | `getCountryReport` | **One-country one-pager** — headline KPIs + trend + cited narrative in one call |
| `databank_get_report_template` | `getReportTemplate` | HTML/CSS layout skeleton + design tokens to fill with one-pager data |
| `databank_get_chunk_context` | — | Neighboring chunks before/after a search result (expand a truncated match) |

**FDRS numeric:** resolve → aggregate_global_trend or get_public_data (`template_id=21` for FDRS-only).  
**UPR documents:** `databank_search_public_documents` — answer only from `chunks[].content`; use `full_coverage=true` for cross-country themes.  
**Counting countries:** never paginate + count by hand — use `databank_get_submission_coverage` (data) or `databank_get_documents_catalog` (documents).  
**One-country one-pager:** `databank_build_country_report` replaces chaining resolve + data + document search; fill `design_template.html_template` — never invent a layout.

Example — volunteers by year:

```text
databank_aggregate_global_trend(query="volunteers")
```

Example — Unified Plan summary:

```text
databank_search_public_documents(query="Syria unified plan 2026 focus areas")
```

Example — "How many countries submitted an annual report through FDRS for 2024, or all years?":

```text
databank_get_submission_coverage(template_id=21, period_name="Annual 2024")   # data
databank_get_documents_catalog(document_type="annual_report")                 # documents, all years
```

Example — country one-pager report:

```text
databank_build_country_report(country="Syria", period_hint="2026 midyear", template_style="default")
```

Example — expand a truncated or ambiguous chunk:

```text
databank_get_chunk_context(chunk_id=17842, before=1, after=1)
```

Do **not** sum raw `databank_get_public_data*` rows for worldwide totals.  
Never set `include_dimensions=true` unless the user explicitly needs join tables.

If MCP tools fail or are unavailable, use the paste workflow below.

---

## How to respond (Claude.ai — follow every time)

When the user asks for Databank data, **do this in your first reply**:

1. One sentence: live API access is blocked here; paste workflow below.
2. Give **curl commands** (not bare `GET` URLs) from the recipes below.
3. Say exactly what to paste back (full JSON, or one file per page if paginated).
4. **Do not** retry curl, `web_fetch`, or `web_search`.
5. **Do not** mention API keys, `include_full_info`, or `per_page=100000` unless
   the user explicitly asks for authenticated/full-dataset access.

Once JSON is pasted, analyze immediately — group, sum, chart, compare.

---

## Blocked in this environment (do not retry)

| Tool | Result |
|------|--------|
| bash/curl | 403 `x-deny-reason: host_not_allowed` |
| web_fetch | URL not in prior search results |
| web_search | `databank.ifrc.org` not indexed |

---

## Public endpoints (no API key)

| Path | Purpose |
|------|---------|
| `/public/global-trend` | Deduped global totals by period (preferred for trends) |
| `/public/indicators/resolve` | Map metric name → indicator id |
| `/public/submissions/coverage` | Count countries with public data by template/period (preferred for counting) |
| `/public/countries/resolve` | Map country name/ISO code/id → reference fields |
| `/public/documents/search` | Public document chunks (UPR plans/reports) |
| `/public/documents/catalog` | Count/list public documents by type/year/country (preferred for counting) |
| `/public/documents/<id>` | One public document's metadata |
| `/indicator-bank` | Indicator catalogue + search |
| `/indicator-bank/<id>` | One indicator's metadata |
| `/data?...` | Submitted values (scoped filters required) |

→ Full schema for all `/public/*` endpoints: [reference.md §2](reference.md)

**Public `/data` rules:** `privacy=public` items only · pagination required
(`page`, `per_page`; max **5000** per page) · no `include_full_info` param ·
no `dynamic_data` / `repeat_data` · header `X-Public-Data-Access: true`.

Context tables are in the same response: `form_items[]`, `countries[]`,
`indicator_bank[]` — use `related=all` to load all matching form items.

---

## Recipe: total volunteers by year (global trend)

Use when the user asks for volunteers over time across all countries.

**Step 1 — user runs, pastes JSON:**
```bash
curl -s "https://databank.ifrc.org/api/v1/indicator-bank?search=volunteers"
```
Pick the indicator whose `name` best matches (e.g. "Number of volunteers").
There may be several — confirm with the user if ambiguous. Note its `id`.

**Step 2 — user runs one curl per page, pastes each JSON** (replace `ID`):
```bash
curl -s "https://databank.ifrc.org/api/v1/data?indicator_bank_id=ID&related=all&page=1&per_page=5000"
curl -s "https://databank.ifrc.org/api/v1/data?indicator_bank_id=ID&related=all&page=2&per_page=5000"
```
Stop when `current_page >= total_pages`. Browser works too: paste the same URL
in the address bar.

**Step 3 — you analyze pasted JSON:**
- Filter `data[]` where `data_status == "available"`.
- Group by `period_name`; sum `num_value` (or parse `value`) across all countries for **counts**. Percentage-type indicators use a **0–1 decimal** (`25` stored → `0.25`); do not divide again, and do not sum percentages.
- Sort periods chronologically (e.g. "Annual 2020" … "Annual 2024").
- Output a table and/or trend summary. Use `countries[]` only if country breakdown
  is requested.

Do **not** use `include_full_info=true` (ignored). Do **not** suggest
`per_page=100000` without an API key.

---

## Recipe: how many countries submitted X (counting)

Use when the user asks **"how many countries/National Societies submitted..."**
— for data ("FDRS data", "volunteer figures") or documents ("annual report",
"Unified Plan"). Both compact endpoints return the count directly; no
pagination or manual counting needed.

**Data submitted** (one curl, paste JSON):
```bash
curl -s "https://databank.ifrc.org/api/v1/public/submissions/coverage?template_id=21&period_name=Annual%202024"
```
Omit `period_name` for a `by_period[]` breakdown across all years. Read
**`countries_submitted_total`** (all years in scope) or per-year counts from
**`by_period[]`**. `template_id=21` is FDRS; `22`/`24` is UPR.

**Document submitted** (annual report / Unified Plan file itself):
```bash
curl -s "https://databank.ifrc.org/api/v1/public/documents/catalog?document_type=annual_report&year=2024"
```
Omit `year` for a `by_year[]` breakdown across all years. Read
**`countries_count`** / **`total_documents`**; use `document_type=unified_plan`
for UPR. Add `&include_documents=false` for counts only (smaller paste).

Both reflect **public coverage only** (a public value, or a document marked
public in the Knowledge Base) — never internal assignment/workflow status,
which is not exposed by any public endpoint. If the user's phrasing is
ambiguous between "submitted data" and "submitted a report", ask, or answer
both and label each clearly.

→ Full schema: [reference.md §2](reference.md)

---

## Recipe: one indicator, one period, all countries

```bash
curl -s "https://databank.ifrc.org/api/v1/indicator-bank?search=volunteers"
curl -s "https://databank.ifrc.org/api/v1/data?indicator_bank_id=ID&period_name=Annual%202023&related=all&page=1&per_page=5000"
```

---

## Recipe: one country

```bash
curl -s "https://databank.ifrc.org/api/v1/data?indicator_bank_id=ID&country_iso3=BGD&related=all&page=1&per_page=5000"
```

---

## Indicator Bank fields

Search/filter: `search`, `type`, `sector`, `sub_sector`, `emergency`, `archived`.

Each indicator: `id`, `name`, `definition`, `type`, `unit`, `sector`, `sub_sector`,
`fdrs_kpi_code`, `tags`, translations, `disaggregation_guidance`.

→ Full schema: [reference.md §1](reference.md)

---

## Tips

- If user already pasted/uploaded JSON, skip curl — analyze immediately.
- Unscoped `/data` (no filters) returns **401** — always include `indicator_bank_id` or similar.
- FDRS template id is **21** when filtering by template; UPR is `22`/`24`.
- "How many countries submitted..." → `/public/submissions/coverage` or
  `/public/documents/catalog` — never paginate `/data` or document search just to count.
- Authenticated access (API key, larger exports) only when user explicitly requests it.
