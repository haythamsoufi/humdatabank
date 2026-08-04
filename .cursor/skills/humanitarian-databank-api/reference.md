# Humanitarian Databank — Public API Reference

**Base URL:** `https://databank.ifrc.org/api/v1`

**Scope:** Endpoints that work without authentication. All other routes return 401.

---

## §0 Claude.ai / sandbox environments

Many AI chat interfaces **block outbound HTTP** to `databank.ifrc.org`. If live
fetch fails with an egress or permissions error:

1. Provide the user a curl command to run locally.
2. Ask them to paste the JSON response into the chat.
3. Proceed using the pasted data — do not retry fetch loops.

Cursor agents with open network access can fetch URLs directly.

---

## §1 Indicator Bank

### `GET /api/v1/indicator-bank`

No authentication. Cached 5 minutes.

**Query parameters**

| Param | Type | Description |
|-------|------|-------------|
| `search` | string | Full-text search on `name` and `definition` |
| `type` | string | `"Number"`, `"Percentage"`, `"Ratio"`, etc. |
| `sector` | string | Sector name (e.g. `"Health"`) |
| `sub_sector` | string | Sub-sector name |
| `emergency` | string | `"true"` — emergency indicators only |
| `archived` | string | `"true"` / `"false"` / omit for all |

**Response**

```json
{
  "indicators": [
    {
      "id": 42,
      "name": "Number of volunteers",
      "type": "Number",
      "type_translations": { "fr": "Nombre" },
      "unit": "People",
      "unit_translations": { "fr": "Personnes" },
      "fdrs_kpi_code": "VO001",
      "definition": "Total active Red Cross/Crescent volunteers.",
      "aggregated_label": null,
      "aggregated_label_translations": null,
      "area": "People",
      "area_label": "People Reached",
      "spef_label": "People Reached",
      "data_source": null,
      "disaggregation_guidance": null,
      "monitoring_questions": [],
      "tags": ["volunteers"],
      "name_translations": { "fr": "Nombre de volontaires" },
      "definition_translations": {},
      "sector": { "primary": "Organizational Capacity", "secondary": null, "tertiary": null },
      "sub_sector": { "primary": "Volunteers", "secondary": null, "tertiary": null },
      "emergency": false,
      "related_programs": [],
      "archived": false,
      "created_at": "2021-03-15T10:00:00",
      "updated_at": "2023-08-01T14:30:00"
    }
  ]
}
```

### `GET /api/v1/indicator-bank/<indicator_id>`

Single indicator object (same shape, not wrapped in `"indicators"`).

---

## §2 Public Data (`GET /api/v1/data`)

Submitted form values plus dimension tables. **No API key** when scoped filters
are provided. Returns only form items marked `privacy=public`.

### Required for public access

At least one scope filter:

| Param | Description |
|-------|-------------|
| `indicator_bank_id` | Single indicator |
| `indicator_bank_ids` | Comma-separated ids (e.g. `"42,729"`) |
| `template_id` | Form template (FDRS = `21`) |
| `country_id` | Numeric country id |
| `country_iso2` | 2-letter ISO (e.g. `BD`) |
| `country_iso3` | 3-letter ISO (e.g. `BGD`) |
| `period_name` | Reporting period (e.g. `Annual 2023`) |
| `submission_id`, `assignment_id`, `item_id` | Narrow scopes |

Unscoped requests (no filters) return **401**.

### Public access restrictions

| Rule | Detail |
|------|--------|
| Privacy | Only `privacy=public` form items |
| Pagination | Always on; default `page=1`, `per_page=20`; max `5000` |
| Blocked | `analysis=true`, `include_non_reported=true` |
| Omitted | `dynamic_data[]`, `repeat_data[]` |
| Header | `X-Public-Data-Access: true` |

Authenticated callers (API key / session) bypass these restrictions.

### Query parameters (public + authenticated)

| Param | Type | Description |
|-------|------|-------------|
| `indicator_bank_id` | int | Filter by indicator |
| `indicator_bank_ids` | string | Comma-separated indicator ids |
| `template_id` | int | Filter by form template |
| `country_id` | int | Filter by country |
| `country_iso2` | string | Filter by ISO-2 |
| `country_iso3` | string | Filter by ISO-3 |
| `period_name` | string | Filter by reporting period |
| `submission_type` | string | `"assigned"` or `"public"` |
| `item_id` | int | Specific form item |
| `item_type` | string | `"indicator"`, `"question"`, `"document_field"` |
| `related` | string | `"page"` (default) or `"all"` — scopes `form_items[]` |
| `layout` | string | `"flat"` (default) or `"star"` |
| `sort` | string | `submitted_at`, `template_id`, `country_id`, `period_name` |
| `order` | string | `desc` (default) or `asc` |
| `page` / `per_page` | int | Pagination |
| `date_from` / `date_to` | string | ISO date bounds on `submitted_at` |

### Flat response shape

```json
{
  "data": [
    {
      "id": 890123,
      "submission_type": "assigned",
      "submission_id": 45,
      "form_item_id": 1234,
      "template_id": 21,
      "period_name": "Annual 2023",
      "country_id": 14,
      "value": "45000",
      "num_value": 45000.0,
      "data_status": "available",
      "date_collected": "2024-02-10T12:00:00",
      "submitted_at": "2024-02-10T12:00:00",
      "disaggregation_data": {
        "mode": "standard",
        "values": { "male_0_17": 12000, "female_0_17": 11500 }
      }
    }
  ],
  "form_items": [],
  "countries": [],
  "national_societies": [],
  "indicator_bank": [],
  "matrix_cells": [],
  "assignment_statuses": [],
  "arrays": {},
  "total_items": 150,
  "total_pages": 8,
  "current_page": 1,
  "per_page": 20
}
```

### `data_status` values

| Value | Meaning |
|-------|---------|
| `"available"` | Value reported |
| `"data_not_available"` | Marked unavailable |
| `"not_applicable"` | Marked N/A |

### Star layout (`layout=star`)

Returns `data.schema_version: "1.1"` with dimensional tables under
`data.tables` (`fact_form_values`, `dim_country`, `dim_form_item`, etc.).

### Examples

```
GET /api/v1/data?indicator_bank_id=42&period_name=Annual%202023&page=1&per_page=500
GET /api/v1/data?template_id=21&country_iso3=BGD&period_name=Annual%202023&related=all
GET /api/v1/data?indicator_bank_ids=42,729&period_name=Annual%202023
```

---

## §3 Authenticated-only endpoints

These return **401** without an API key:

| Endpoint | Use public alternative |
|----------|------------------------|
| `GET /api/v1/data` (unscoped) | Add scope filters |
| `GET /api/v1/periods` | Derive periods from `/data` rows or indicator-bank context |
| `GET /api/v1/countrymap` | Use `countries[]` from scoped `/data` response |
| `GET /api/v1/templates` | Requires API key |
| `GET /api/v1/form-items` | Requires API key |
| `GET /api/v1/sectors` | Use sector fields on indicator-bank entries |

Full dataset access: `Authorization: Bearer YOUR_KEY` or `?api_key=YOUR_KEY`.

---

## §4 Error responses

```json
{ "error": "Authentication required for unscoped data requests...", "status": 401 }
{ "error": "Indicator not found", "status": 404 }
```

Rate limit exceeded: HTTP 429.
