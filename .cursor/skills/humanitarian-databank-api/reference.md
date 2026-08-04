# Humanitarian Databank — Public API Reference

**Scope:** Endpoints that work without authentication. All other `/api/v1/*`
routes return 401 unless an API key or session is supplied.

**Production bases:**
- `https://databank.ifrc.org/api/v1`
- `https://databank.ifrc.org/api/mobile/v1`

---

## §1 Indicator Bank (`/api/v1`)

### `GET /api/v1/indicator-bank`

Returns the indicator catalogue. Cached 5 minutes (`Cache-Control: public, max-age=300`).

**Query parameters**

| Param | Type | Description |
|-------|------|-------------|
| `search` | string | Full-text search on `name` and `definition` |
| `type` | string | Measurement type (e.g. `"Number"`, `"Percentage"`, `"Ratio"`) |
| `sector` | string | Primary sector name (e.g. `"Health"`) |
| `sub_sector` | string | Sub-sector name |
| `emergency` | string | `"true"` — only emergency-tagged indicators |
| `archived` | string | `"true"` archived only; `"false"` active only; omit = all |

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
      "aggregated_label_translations": null,
      "area": "People",
      "area_label": "People Reached",
      "spef_label": "People Reached",
      "data_source": null,
      "disaggregation_guidance": null,
      "monitoring_questions": [],
      "tags": ["volunteers", "capacity"],
      "name_translations": { "fr": "Nombre de volontaires" },
      "definition_translations": { "fr": "..." },
      "sector": {
        "primary": "Organizational Capacity",
        "secondary": null,
        "tertiary": null
      },
      "sub_sector": {
        "primary": "Volunteers",
        "secondary": null,
        "tertiary": null
      },
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

Returns a single indicator object (same shape as one array item above — not wrapped
in `"indicators"`). HTTP 404 if not found.

---

## §2 Mobile API Envelope

All `/api/mobile/v1/data/*` routes use this shape:

**Success:**
```json
{
  "success": true,
  "data": { },
  "meta": { }
}
```

**Paginated list** (`data` is the array directly):
```json
{
  "success": true,
  "data": [ ... ],
  "meta": {
    "total": 1500,
    "page": 1,
    "per_page": 500,
    "total_pages": 3
  }
}
```

**Error:**
```json
{
  "success": false,
  "error": "indicator_bank_id is required",
  "error_code": "VALIDATION_ERROR"
}
```

Rate limits apply (typically 30–120 requests/minute per IP depending on route).

---

## §3 Countries

### `GET /api/mobile/v1/data/countrymap`

**Query parameters**

| Param | Type | Description |
|-------|------|-------------|
| `locale` | string | Language code for country names (default `"en"`) |

**Response**

```json
{
  "success": true,
  "data": {
    "countries": [
      {
        "id": 14,
        "name": "Afghanistan",
        "iso2": "AF",
        "iso3": "AFG",
        "region": "Asia Pacific"
      }
    ]
  },
  "meta": { "total": 192 }
}
```

> **Note:** `/api/v1/countrymap` returns richer localized data but **requires
> authentication**. Use this mobile endpoint for public access.

---

## §4 Sectors and Sub-sectors

### `GET /api/mobile/v1/data/sectors-subsectors`

No query parameters.

**Response**

```json
{
  "success": true,
  "data": {
    "sectors": [
      {
        "id": 1,
        "name": "Health",
        "description": "...",
        "display_order": 1,
        "logo_url": "https://databank.ifrc.org/api/v1/uploads/sectors/health.png",
        "icon_class": "fa-heart",
        "multilingual_names": { "fr": "Santé", "es": "Salud" },
        "subsectors": [
          {
            "id": 10,
            "name": "First Aid",
            "description": "...",
            "display_order": 1,
            "multilingual_names": { "fr": "Premiers secours" },
            "sector_id": 1
          }
        ]
      }
    ]
  }
}
```

Sector logo URLs point to public `GET /api/v1/uploads/sectors/<filename>` (binary
image stream, no auth).

---

## §5 Periods

### `GET /api/mobile/v1/data/periods`

Returns distinct reporting period labels, newest first.

**Query parameters**

| Param | Type | Description |
|-------|------|-------------|
| `template_id` | int | Form template (default `21` = FDRS) |
| `country_id` | int | Scope to one country's assignments |

**Response**

```json
{
  "success": true,
  "data": {
    "periods": ["Annual 2024", "Annual 2023", "Annual 2022"]
  }
}
```

> **Note:** `/api/v1/periods` returns the same data as a bare JSON array but
> **requires authentication**.

---

## §6 FDRS Overview (reported values)

### `GET /api/mobile/v1/data/fdrs-overview`

Pre-aggregated numeric totals per country for one indicator. This is the public
replacement for authenticated `/api/v1/data` queries.

**Query parameters**

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `indicator_bank_id` | int | **yes** | Indicator to aggregate |
| `template_id` | int | no | Form template (default `21` = FDRS) |
| `period_name` | string | no | Reporting period label |
| `locale` | string | no | Localized country names (default `"en"`) |

**Response**

```json
{
  "success": true,
  "data": {
    "period_name": "Annual 2023",
    "by_country": {
      "14": 45000,
      "23": 120000
    },
    "country_names": {
      "14": "Afghanistan",
      "23": "Bangladesh"
    },
    "country_iso2": {
      "14": "AF",
      "23": "BD"
    }
  }
}
```

- `by_country` keys are country ids (strings); values are summed numeric totals.
- Only rows with reported numeric values are included (excludes "data not
  available" and "not applicable").
- Aggregates both official assigned submissions and public submissions.

**Example — volunteers in 2023:**
```
GET /api/mobile/v1/data/fdrs-overview?indicator_bank_id=42&period_name=Annual%202023
```

---

## §7 Disaggregation Overview

### `GET /api/mobile/v1/data/disaggregation-overview`

Pre-aggregated sex/age/regional breakdown. Anonymous callers receive global and
regional aggregates only (`by_country` is empty).

**Query parameters**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `indicator_bank_id` | int | `729` | Indicator to aggregate |
| `template_id` | int | `21` | Form template |
| `period_name` | string | — | Reporting period |
| `locale` | string | `"en"` | Localized labels |

**Response (anonymous)**

```json
{
  "success": true,
  "data": {
    "period_name": "Annual 2023",
    "indicator_bank_id": 729,
    "total": 125000000,
    "record_count": 850,
    "disaggregated_count": 620,
    "disaggregation_rate": 72.9,
    "by_sex": [
      { "category": "female", "value": 67000000 },
      { "category": "male", "value": 58000000 }
    ],
    "by_age": [
      { "category": "18_plus", "value": 80000000 },
      { "category": "0_17", "value": 45000000 }
    ],
    "by_country": [],
    "by_region": [
      {
        "region": "Africa",
        "value": 35000000,
        "record_count": 180,
        "disaggregated_count": 140,
        "disaggregation_rate": 77.8,
        "country_count": 54
      }
    ],
    "trends": [
      {
        "period": "Annual 2023",
        "total": 125000000,
        "record_count": 850,
        "disaggregated_count": 620,
        "disaggregation_rate": 72.9
      }
    ],
    "country_details_available": false
  }
}
```

---

## §8 Resources and Publications

### `GET /api/mobile/v1/data/resources`

**Query parameters**

| Param | Type | Description |
|-------|------|-------------|
| `page` | int | Page number (default 1) |
| `per_page` | int | Page size (default 20, max 100) |
| `search` | string | Filter by title |
| `type` | string | `publication`, `resource`, `document`, or `other` |
| `locale` | string | Language for title/description (default `"en"`) |
| `grouped` | bool | When `true` and no search, return `data.sections[]` by subcategory |

**Flat response (paginated)**

```json
{
  "success": true,
  "data": [
    {
      "id": 5,
      "title": "FDRS Guidance 2024",
      "description": "...",
      "resource_type": "publication",
      "publication_date": "2024-01-15",
      "file_url": "https://databank.ifrc.org/resources/download/5/en",
      "thumbnail_url": "https://databank.ifrc.org/resources/thumbnail/5/en",
      "available_languages": ["en", "fr", "es"],
      "file_languages": ["en", "fr"],
      "subcategory": { "id": 2, "name": "Guidance", "display_order": 1 }
    }
  ],
  "meta": { "total": 42, "page": 1, "per_page": 20, "total_pages": 3 }
}
```

---

## §9 Mobile Indicator Bank (paginated alternative)

### `GET /api/mobile/v1/data/indicator-bank`

Same indicator objects as §1, with pagination.

**Query parameters:** all §1 filters plus:

| Param | Type | Description |
|-------|------|-------------|
| `page` | int | Page number (default 1) |
| `per_page` | int | Page size (default 500, max 2000) |
| `sector_id` | int | Filter by sector numeric id |

### `GET /api/mobile/v1/data/indicator-bank/<id>`

```json
{
  "success": true,
  "data": { "indicator": { /* same shape as §1 */ } }
}
```

---

## §10 Common Query Examples

**Find an indicator, then get its FDRS totals:**
```
GET /api/v1/indicator-bank?search=people%20reached
GET /api/mobile/v1/data/periods
GET /api/mobile/v1/data/fdrs-overview?indicator_bank_id=729&period_name=Annual%202023
```

**Compare sectors:**
```
GET /api/v1/indicator-bank?sector=Health&archived=false
GET /api/mobile/v1/data/sectors-subsectors
```

**Regional disaggregation for people reached:**
```
GET /api/mobile/v1/data/disaggregation-overview?period_name=Annual%202023
```

**Look up a country by ISO code, then map FDRS totals:**
```
GET /api/mobile/v1/data/countrymap
# find country id for iso2=BD (23)
GET /api/mobile/v1/data/fdrs-overview?indicator_bank_id=42&period_name=Annual%202023
# read data.by_country["23"]
```

---

## §11 Error Responses

**v1 endpoints** return plain JSON errors:
```json
{ "error": "Indicator not found", "status": 404 }
```

**Mobile endpoints** use the envelope:
```json
{ "success": false, "error": "indicator_bank_id is required" }
```

HTTP 429 when rate limits are exceeded.

---

## §12 Endpoints That Require Authentication

Do **not** call these without an API key — they will return 401:

| Endpoint | Why it fails publicly |
|----------|----------------------|
| `GET /api/v1/data` | Raw FormData rows — auth required |
| `GET /api/v1/data/tables` | Redirects to `/data` — auth required |
| `GET /api/v1/periods` | Use mobile `/data/periods` instead |
| `GET /api/v1/countrymap` | Use mobile `/data/countrymap` instead |
| `GET /api/v1/templates` | Form structure metadata |
| `GET /api/v1/form-items` | Form item details |
| `GET /api/v1/submissions` | Submission records |
| `GET /api/v1/sectors` | Use mobile `/data/sectors-subsectors` instead |
| `GET /api/v1/resources` | Use mobile `/data/resources` instead |
| `GET /Indicator/*` (legacy) | Blazor compat layer — API key required |

For programmatic access to raw data exports, contact IFRC for an API key.
