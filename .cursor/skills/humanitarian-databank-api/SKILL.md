---
name: humanitarian-databank-api
description: >-
  IFRC Humanitarian Databank public API (no auth): indicator bank metadata and
  scoped /api/v1/data. Claude.ai cannot fetch live — user must paste JSON.
---

# Humanitarian Databank — Public API

**Base URL:** `https://databank.ifrc.org/api/v1`

Full schemas: [reference.md](reference.md).

---

## Important: Claude.ai network limits

Claude.ai **cannot** call `databank.ifrc.org` directly. Its sandbox blocks
outbound HTTP to non-allowlisted hosts, and `web_fetch` only works on URLs
already surfaced by search or pasted by the user.

**When running in Claude.ai:**

1. Ask the user to run the curl command below and paste the JSON response, **or**
2. Use data the user already pasted in the conversation.

**When running in Cursor** (or any environment with open network access), fetch
the URLs directly.

Example for the user to run locally:

```bash
curl -s "https://databank.ifrc.org/api/v1/indicator-bank?search=volunteers"
curl -s "https://databank.ifrc.org/api/v1/data?indicator_bank_id=42&period_name=Annual%202023&page=1&per_page=100"
```

---

## Public endpoints (no API key)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/indicator-bank` | Full indicator catalogue with filters |
| GET | `/indicator-bank/<id>` | Single indicator metadata |
| GET | `/data?...` | Submitted values — **scoped filters required** |

All other `/api/v1/*` routes require authentication.

---

## Public data access (`GET /api/v1/data`)

Works **without an API key** when at least one scope filter is provided:

- `indicator_bank_id` or `indicator_bank_ids`
- `template_id`
- `country_id`, `country_iso2`, or `country_iso3`
- `period_name`
- `submission_id`, `assignment_id`, `item_id`

**Restrictions for unauthenticated access:**

- Returns only form items with `privacy=public` (same data shown on the public website)
- Pagination is always applied (`page`, `per_page`; max 5000 per page)
- `analysis` and `include_non_reported` require authentication
- `dynamic_data` and `repeat_data` are omitted

Response includes dimension tables: `data[]`, `form_items[]`, `countries[]`,
`national_societies[]`, `indicator_bank[]`, `matrix_cells[]`, plus pagination
metadata. Header `X-Public-Data-Access: true` confirms public mode.

For full dataset access (all form items, no scope requirement), use an API key:
`Authorization: Bearer YOUR_KEY` or `?api_key=YOUR_KEY`.

→ Full parameter reference: [reference.md §2](reference.md)

---

## Workflow — indicator values by country and period

**Step 1** — Find the indicator id:
```
GET /api/v1/indicator-bank?search=volunteers
```

**Step 2** — Fetch submitted values (public, scoped):
```
GET /api/v1/data?indicator_bank_id=42&period_name=Annual%202023&page=1&per_page=500
```

**Step 3** — Filter to one country:
```
GET /api/v1/data?indicator_bank_id=42&country_iso3=BGD&period_name=Annual%202023
```

Use `related=all` to include all matching `form_items[]` for the filtered dataset.

---

## Indicator Bank metadata

```
GET /api/v1/indicator-bank?search=volunteers
GET /api/v1/indicator-bank?sector=Health&type=Number&archived=false
GET /api/v1/indicator-bank/42
```

Each indicator includes: name, definition, type, unit, sector/sub-sector,
FDRS KPI code, tags, translations, disaggregation guidance, monitoring questions.

→ Field reference: [reference.md §1](reference.md)

---

## Tips

- Unscoped `GET /api/v1/data` (no filters) returns **401** — always include a scope filter for public access.
- Prefer `country_iso2` / `country_iso3` over numeric `country_id` when you only know the ISO code.
- FDRS annual reporting uses `template_id=21` when scoping by template.
- In Claude.ai, never attempt curl/fetch to databank.ifrc.org — ask the user to paste JSON instead.
