# Humanitarian Databank API — Reference

**Base URL:** `https://databank.ifrc.org/api/v1`

---

## §1 Indicator Bank

### `GET /api/v1/indicator-bank`

Returns the full indicator catalogue in one call. No authentication required.

**Query parameters**

| Param | Type | Description |
|-------|------|-------------|
| `search` | string | Full-text search on `name` and `definition` |
| `type` | string | Indicator type label (e.g. `"Number"`, `"Percentage"`, `"Ratio"`) |
| `sector` | string | Sector name (e.g. `"Health"`, `"Disaster Management"`) |
| `sub_sector` | string | Sub-sector name |
| `emergency` | string | `"true"` to return only emergency-tagged indicators |
| `archived` | string | `"true"` = only archived; `"false"` = only active; omit = all |

**Response**

```json
{
  "indicators": [
    {
      "id": 42,
      "name": "Number of volunteers",
      "type": "Number",
      "type_translations": { "fr": "Nombre", "es": "Número" },
      "unit": "People",
      "unit_translations": { "fr": "Personnes" },
      "fdrs_kpi_code": "VO001",
      "definition": "Total active Red Cross/Crescent volunteers.",
      "aggregated_label": null,
      "area": "People",
      "area_label": "People Reached",
      "data_source": null,
      "disaggregation_guidance": null,
      "monitoring_questions": [],
      "tags": ["volunteers", "capacity"],
      "name_translations": { "fr": "Nombre de volontaires" },
      "definition_translations": { "fr": "..." },
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

Returns a single indicator (same shape as an array item above — not wrapped in
`"indicators"`).

---

## §2 `/api/v1/data`

Returns raw `FormData` rows. No API key required for public-data access
(unscoped, unpaginated). API-key auth enables pagination and full dataset
access.

### Query parameters

| Param | Type | Description |
|-------|------|-------------|
| `indicator_bank_id` | int | Filter by indicator bank entry |
| `template_id` | int | Filter by form template |
| `item_id` | int | Filter by specific form item |
| `item_type` | string | `"indicator"`, `"question"`, or `"document_field"` |
| `country_id` | int | Filter by country (numeric ID) |
| `country_iso2` | string | Filter by 2-letter ISO code (resolved to `country_id`) |
| `country_iso3` | string | Filter by 3-letter ISO code (resolved to `country_id`) |
| `submission_id` | int | Filter by submission (AssignmentEntityStatus ID) |
| `submission_type` | string | `"assigned"` or `"public"` |
| `period_name` | string | Filter by reporting period label |
| `date_from` | string | ISO date/datetime lower bound on `submitted_at` |
| `date_to` | string | ISO date/datetime upper bound on `submitted_at` |
| `include_full_info` | bool | Embed full `form_item_info` in every row |
| `include_dynamic` | bool | Append `dynamic_data[]` (DynamicIndicatorData rows) |
| `include_repeat` | bool | Append `repeat_data[]` (RepeatGroupData rows) |
| `sort` | string | Sort field: `submitted_at` (default), `template_id`, `country_id`, `period_name` |
| `order` | string | `desc` (default) or `asc` |
| `page` | int | Page number (API key auth only, default 1) |
| `per_page` | int | Page size (API key auth only, default 20, max 100 000) |

### Response

```json
{
  "data": [ /* FormData rows — see §4 */ ],
  "total_items": 150,
  "total_pages": null,
  "current_page": null,
  "per_page": null
}
```

With API key auth and `page`/`per_page`:
```json
{
  "data": [ ... ],
  "total_items": 3200,
  "total_pages": 32,
  "current_page": 1,
  "per_page": 100
}
```

When `include_dynamic=true`, an extra top-level key is added:
```json
{
  "data": [...],
  "dynamic_data": [
    {
      "data_type": "dynamic",
      "section_id": 5,
      "indicator_bank_id": 42,
      "custom_label": "Volunteers 2023",
      "value": "12000",
      "country_id": 23,
      "period_name": "Annual 2023"
    }
  ]
}
```

When `include_repeat=true`:
```json
{
  "repeat_data": [
    {
      "data_type": "repeat",
      "section_id": 7,
      "repeat_instance_id": 99,
      "instance_number": 1,
      "instance_label": "Branch A",
      "form_item_id": 1234,
      "value": "450"
    }
  ]
}
```

---

## §3 `/api/v1/data/tables`

Like `/data` but bundles related lookup tables (`form_items`, `countries`) in
the same response. Supports a star-schema layout for BI consumers.

### Additional query parameters (beyond those in §2)

| Param | Type | Description |
|-------|------|-------------|
| `related` | string | Scope of related tables: `"page"` (default, current-page rows only) or `"all"` (full filtered dataset) |
| `layout` | string | Response shape: `"flat"` (default) or `"star"` |
| `indicator_bank_ids` | string | Comma-separated indicator bank IDs (e.g. `"42,17,98"`) for multi-indicator fetches |
| `include_non_reported` | bool | Include virtual `"missing"` rows for unreported items (requires `template_id`, `country_id`, `period_name`, `submission_type=assigned`) |
| `analysis` | bool | Enable analysis mode (requires elevated permission) |

### Flat layout response

```json
{
  "data": [ /* FormData rows — see §4 */ ],
  "form_items": [ /* FormItem records — see §5 */ ],
  "countries": [ /* Country records — see §6 */ ],
  "matrix_entity_labels": {
    "1234": { "14": "Afghanistan", "23": "Bangladesh" }
  },
  "total_items": 150,
  "total_pages": null,
  "current_page": null,
  "per_page": null
}
```

`matrix_entity_labels` maps `form_item_id → { row_prefix → display_name }` for
matrix-type indicators whose rows are keyed to National Society or country IDs.

### Star layout response (`layout=star`)

```json
{
  "schema_version": "1.0",
  "grain": "one row per FormData record",
  "tables": {
    "fact_form_values": [ ... ],
    "dim_form_items": [ ... ],
    "dim_countries": [ ... ],
    "bridge_disagg_values": [ ... ]
  }
}
```

---

## §4 FormData Row Schema

Each item in the `data[]` array:

```json
{
  "id": 890123,
  "submission_type": "assigned",
  "submission_id": 45,
  "form_item_id": 1234,
  "template_id": 2,
  "period_name": "Annual 2023",
  "country_id": 14,
  "value": "45000",
  "num_value": 45000.0,
  "data_status": "available",
  "date_collected": "2024-02-10T12:00:00",
  "submitted_at": "2024-02-10T12:00:00",
  "disaggregation_data": {
    "mode": "standard",
    "values": {
      "male_0_17": 12000,
      "female_0_17": 11500,
      "male_18_plus": 12000,
      "female_18_plus": 9500
    }
  },
  "prefilled_value": null,
  "imputed_value": null,
  "prefilled_disaggregation_data": null,
  "imputed_disaggregation_data": null
}
```

For `submission_type: "public"` rows, `assignment_id` is also present.

**`data_status` values:**

| Value | Meaning |
|-------|---------|
| `"available"` | Value was reported |
| `"data_not_available"` | Reporter marked as unavailable |
| `"not_applicable"` | Reporter marked as not applicable |
| `"missing"` | Virtual row — no record exists (only with `include_non_reported=true`) |

**`disaggregation_data.mode` values:**

| Mode | Structure |
|------|-----------|
| `"standard"` | `values` is a flat dict of category-key → numeric value |
| `"matrix"` | `values` keys are `<row_entity_id>_<col_key>`; use `matrix_entity_labels` to resolve row names |
| `"flat"` | `values` is a simple key-value payload |
| `null` | No disaggregation data |

---

## §5 FormItem Record Schema

Appears in `form_items[]` of `/data/tables`, or embedded per-row when
`include_full_info=true`.

```json
{
  "id": 1234,
  "type": "indicator",
  "label": "Number of volunteers",
  "order": 3,
  "display_order": 3,
  "is_required": true,
  "form_item_type": "indicator",
  "layout_column_width": null,
  "layout_break_after": false,
  "section": {
    "id": 10,
    "name": "Organizational Capacity",
    "order": 1,
    "section_type": "standard"
  },
  "template": {
    "id": 2,
    "name": "FDRS Annual Report",
    "description": "..."
  },
  "assignment": {
    "id": 99,
    "period_name": "Annual 2023",
    "assigned_at": "2023-01-01T00:00:00"
  },
  "unit": "People",
  "is_sub_indicator": false,
  "allowed_disaggregation_options": ["by_sex", "by_age"],
  "validation_condition": null,
  "validation_message": null,
  "allow_data_not_available": true,
  "allow_not_applicable": false,
  "allow_disability_questions": false,
  "bank_details": {
    "id": 42,
    "name": "Number of volunteers",
    "type": "Number",
    "unit": "People",
    "definition": "Total active Red Cross/Crescent volunteers.",
    "sector": { "primary": "Organizational Capacity", "secondary": null, "tertiary": null },
    "sub_sector": { "primary": "Volunteers", "secondary": null, "tertiary": null },
    "emergency": false,
    "related_programs": [],
    "archived": false
  }
}
```

`type` / `form_item_type` values: `"indicator"`, `"question"`, `"document_field"`.

For `"question"` items, additional fields: `question_type`, `definition`,
`options`, `lookup_list_id`, `list_display_column`, `list_filters`.

For `"document_field"` items, additional field: `description`.

---

## §6 Country Record Schema

Appears in `countries[]` of `/data/tables`.

```json
{
  "id": 14,
  "name": "Afghanistan",
  "iso3": "AFG",
  "iso2": "AF",
  "national_society_name": "Afghan Red Crescent Society",
  "region": "Asia Pacific",
  "partof": null,
  "status": "active",
  "preferred_language": "fa",
  "currency_code": "AFN",
  "multilingual_names": {
    "fr": "Afghanistan",
    "ar": "أفغانستان",
    "es": "Afganistán"
  },
  "multilingual_national_society_names": {
    "fr": "Croissant-Rouge Afghan"
  }
}
```

---

## §7 Common Query Examples

**All data for one indicator, scoped to a period:**
```
GET /api/v1/data?indicator_bank_id=42&period_name=Annual%202023
```

**All data for one country using ISO code:**
```
GET /api/v1/data?country_iso3=BGD&period_name=Annual%202023
```

**All indicators in a template with form item context:**
```
GET /api/v1/data/tables?template_id=2&period_name=Annual%202023&related=all
```

**Multiple indicators in one request:**
```
GET /api/v1/data/tables?indicator_bank_ids=42,17,98&period_name=Annual%202023
```

**Data with disaggregation breakdown, with context:**
```
GET /api/v1/data/tables
    ?indicator_bank_id=42
    &country_iso2=BD
    &include_full_info=true
```

**Star schema for BI import:**
```
GET /api/v1/data/tables
    ?template_id=2
    &period_name=Annual%202023
    &layout=star
    &related=all
```

**Check what was reported vs. missing for a country/period:**
```
GET /api/v1/data/tables
    ?template_id=2
    &country_id=14
    &period_name=Annual%202023
    &submission_type=assigned
    &include_non_reported=true
```
Rows with `data_status: "missing"` indicate items not yet reported.

**Filter by submission date range:**
```
GET /api/v1/data?template_id=2&date_from=2024-01-01&date_to=2024-06-30
```

---

## §8 Data Model

```
IndicatorBank (id, name, type, unit, sector, sub_sector, emergency, …)
    └── FormItem (id, template_id, version_id, indicator_bank_id, label, section_id, …)
            └── FormData (id, form_item_id, value, data_status, disagg_data, submitted_at)
                    ├── [assigned] via AssignmentEntityStatus
                    │       └── AssignedForm (template_id, period_name)
                    │               → country_id (entity_id on AES)
                    └── [public] via PublicSubmission
                            └── AssignedForm (template_id, period_name)
                                    → country_id (PublicSubmission.country_id)

Country (id, name, iso2, iso3, region, national_society_name, …)
Sector (id, name) → SubSector (id, sector_id, name)
```

- `form_item_id` in a `FormData` row links to `FormItem.id`
- `FormItem.indicator_bank_id` links to `IndicatorBank.id`
- `template_id` on a data row is denormalized from `AssignedForm.template_id`
- `period_name` on a data row is denormalized from `AssignedForm.period_name`
- Published template version scoping: only items from the published version appear in `/data/tables`

---

## §9 Error Responses

```json
{ "error": "Template not found", "status": 404 }
{ "error": "Could not fetch data", "status": 500 }
```

Rate-limit exceeded returns HTTP `429`.
