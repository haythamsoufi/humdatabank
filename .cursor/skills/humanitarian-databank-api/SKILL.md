---
name: humanitarian-databank-api
description: >-
  Query the IFRC Humanitarian Databank public API at databank.ifrc.org to
  retrieve submitted form data, indicator values, disaggregation breakdowns,
  form item details, countries, and reporting periods. Use when asked about
  IFRC Red Cross data, FDRS data, indicator values by country or period,
  form submissions, humanitarian indicators, or when the user wants to explore
  or analyse data from the Humanitarian Databank. No API key required for
  public data.
---

# Humanitarian Databank API

The IFRC Humanitarian Databank holds data reported by National Red Cross and
Red Crescent Societies worldwide.

**Base URL:** `https://databank.ifrc.org/api/v1`

Full endpoint schemas and response examples are in [reference.md](reference.md).

---

## Core Concepts

| Concept | Description |
|---------|-------------|
| **Indicator Bank** | Master catalogue of measurable humanitarian indicators (e.g. "Number of volunteers"). Each entry has a stable numeric `id`. |
| **Template** | A form containing a set of indicators (form items) grouped into sections. Each template has a `template_id`. |
| **Form Item** | One indicator (or question/document field) within a template version. Has `form_item_id`, `indicator_bank_id`, `label`, `section`. |
| **Assignment Period** | Reporting period label string (e.g. `"Annual 2023"`, `"FY2024"`). Passed as `period_name`. |
| **Submission** | A country's completed form for a given template and period. `submission_type` is `"assigned"` (official) or `"public"` (open). |
| **FormData** | A single cell of data: one form item × one submission × one country. Carries `value`, `data_status`, `disaggregation_data`. |
| **Disaggregation** | Breakdown of a numeric value by demographic categories (e.g. by sex/age), stored under `disaggregation_data.values`. |

---

## Endpoints

### `GET /api/v1/indicator-bank`
Browse the indicator catalogue (no auth). Use this to find `indicator_bank_id`
values before querying `/data`.
→ See [reference.md §1](reference.md) for params and response shape.

### `GET /api/v1/indicator-bank/<id>`
Single indicator details (no auth).

### `GET /api/v1/data`
Returns raw FormData rows with optional filtering. Use this to retrieve
submitted values per indicator, country, and period.
→ See [reference.md §2](reference.md) for all params, filtering, and response shape.

### `GET /api/v1/data/tables`
Like `/data` but adds related lookup tables (`form_items`, `countries`) in the
same response. Supports a star-schema layout for BI consumers.
→ See [reference.md §3](reference.md).

---

## Workflow 1 — Get values for a specific indicator

**Step 1** — Find the indicator ID:
```
GET /api/v1/indicator-bank?search=volunteers
```
Note the `id` of the target indicator (e.g. `42`).

**Step 2** — Fetch all data rows for that indicator:
```
GET /api/v1/data?indicator_bank_id=42
```

**Step 3** — Scope to a period:
```
GET /api/v1/data?indicator_bank_id=42&period_name=Annual%202023
```

---

## Workflow 2 — Get data for a country

Use ISO codes directly — no need to look up country IDs first:
```
GET /api/v1/data?country_iso2=BD&period_name=Annual%202023
GET /api/v1/data?country_iso3=BGD&indicator_bank_id=42
```
Or by numeric `country_id`:
```
GET /api/v1/data?country_id=23&indicator_bank_id=42
```

---

## Workflow 3 — Get data with full context (form items + countries)

`/data/tables` bundles the related lookup tables so you don't need separate
calls:
```
GET /api/v1/data/tables
    ?indicator_bank_id=42
    &period_name=Annual%202023
    &related=all
```
Response includes `data[]`, `form_items[]`, and `countries[]`.

---

## Workflow 4 — Explore what indicators a template contains

```
GET /api/v1/data/tables
    ?template_id=2
    &period_name=Annual%202023
    &related=all
```
`form_items[]` in the response lists every indicator (with label, section, unit,
bank details) that has data for that template and period.

---

## Key Query Parameters for `/data` and `/data/tables`

| Param | Type | Description |
|-------|------|-------------|
| `indicator_bank_id` | int | Filter to one indicator (cross-template) |
| `template_id` | int | Filter to one form template |
| `country_id` | int | Filter to one country (numeric ID) |
| `country_iso2` | string | Filter to one country by 2-letter ISO code |
| `country_iso3` | string | Filter to one country by 3-letter ISO code |
| `period_name` | string | Filter to one reporting period label |
| `submission_type` | string | `"assigned"` or `"public"` |
| `item_id` | int | Filter to a specific form item ID |
| `item_type` | string | `"indicator"`, `"question"`, or `"document_field"` |
| `submission_id` | int | Filter to a specific submission |
| `date_from` | string | ISO date lower bound on `submitted_at` |
| `date_to` | string | ISO date upper bound on `submitted_at` |
| `include_full_info` | bool | Embed full form item info in each data row |
| `include_dynamic` | bool | Add `dynamic_data[]` array to response |
| `include_repeat` | bool | Add `repeat_data[]` array to response |
| `sort` | string | `submitted_at` (default), `template_id`, `country_id`, `period_name` |
| `order` | string | `desc` (default) or `asc` |
| `page` / `per_page` | int | Pagination (API key auth only; default 20, max 100 000) |
| `related` | string | `/data/tables` only: `"page"` (default) or `"all"` — scopes `form_items[]`. `countries[]` always returns all countries. |
| `layout` | string | `/data/tables` only: `"flat"` (default) or `"star"` |

---

## `data_status` Values

| Value | Meaning |
|-------|---------|
| `"available"` | Value was reported |
| `"data_not_available"` | Reporter marked this as unavailable |
| `"not_applicable"` | Reporter marked this as not applicable |
| `"missing"` | No FormData row exists (virtual row when `include_non_reported=true`) |

---

## Tips

- Always filter by at least one of `indicator_bank_id`, `template_id`, `country_id`, or `period_name` to keep responses manageable.
- Use `country_iso2` / `country_iso3` instead of `country_id` when you only know the ISO code.
- `/data/tables?related=all` returns form items for the **entire filtered dataset**, not just the current page. `countries[]` always includes the full country dimension.
- `include_full_info=true` embeds `form_item_info` (label, section, unit, indicator bank details) directly in each row, avoiding a second call.
- `indicator_bank_ids` (comma-separated) on `/data/tables` lets you fetch multiple indicators in one request.
- Disaggregation keys under `disaggregation_data.values` vary by indicator configuration. The `mode` field (`"standard"`, `"matrix"`, or `"flat"`) describes the structure.
