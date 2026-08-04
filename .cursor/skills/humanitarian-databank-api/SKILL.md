---
name: humanitarian-databank-api
description: >-
  Paste-first IFRC Databank analysis. Give user curl commands immediately; parse
  pasted JSON. Public /api/v1 only. Never live-fetch databank.ifrc.org.
---

# Humanitarian Databank — Public API

**Base URL:** `https://databank.ifrc.org/api/v1`

**Mode:** User runs curl (or browser) → pastes JSON → you analyze.  
**Or:** use the **humanitarian-databank MCP connector** when enabled (live fetch).  
Full schemas: [reference.md](reference.md).

---

## MCP connector (preferred when available)

If the **humanitarian-databank** MCP tools are connected, call them directly —
do not curl or web_fetch:

| Tool | Use for |
|------|---------|
| `databank_aggregate_global_trend` | **Global totals by year** (deduped; preferred) |
| `databank_resolve_indicator` | Map "volunteers" / "staff" → indicator id |
| `databank_search_indicators` | Find indicator ids by keyword (ranked, capped) |
| `databank_get_indicator` | Full metadata for one id |
| `databank_get_public_data` | One page of scoped public data (raw rows) |
| `databank_get_public_data_all_pages` | Raw multi-page export (not deduped) |

Example flow for volunteers by year:

```text
databank_aggregate_global_trend(query="volunteers")
```

One call returns `by_period` with deduplicated global totals. Do **not** sum raw
`databank_get_public_data*` rows — multiple submissions per country+period exist.

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
| `/indicator-bank` | Indicator catalogue + search |
| `/indicator-bank/<id>` | One indicator's metadata |
| `/data?...` | Submitted values (scoped filters required) |

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
- Group by `period_name`; sum `num_value` (or parse `value`) across all countries.
- Sort periods chronologically (e.g. "Annual 2020" … "Annual 2024").
- Output a table and/or trend summary. Use `countries[]` only if country breakdown
  is requested.

Do **not** use `include_full_info=true` (ignored). Do **not** suggest
`per_page=100000` without an API key.

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
- FDRS template id is **21** when filtering by template.
- Authenticated access (API key, larger exports) only when user explicitly requests it.
