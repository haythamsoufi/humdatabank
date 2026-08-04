---
name: humanitarian-databank-api
description: >-
  Query IFRC Humanitarian Databank public APIs (no auth): indicator bank
  metadata, countries, sectors, FDRS totals, disaggregation, publications.
---

# Humanitarian Databank — Public API

The IFRC Humanitarian Databank holds data reported by National Red Cross and
Red Crescent Societies worldwide.

**This skill covers public endpoints only — no API key, no login.**

Most `/api/v1/data` routes and catalog endpoints (`/periods`, `/countrymap`,
`/templates`, `/form-items`, etc.) **require authentication** and will return
401. Do not call them from this skill.

Full schemas and examples: [reference.md](reference.md).

---

## API Surfaces

| Base URL | Use for |
|----------|---------|
| `https://databank.ifrc.org/api/v1` | Indicator Bank catalogue (list + detail) |
| `https://databank.ifrc.org/api/mobile/v1` | Countries, sectors, periods, FDRS totals, disaggregation, publications |

Mobile routes return a standard envelope:

```json
{ "success": true, "data": { ... }, "meta": { ... } }
```

On error: `{ "success": false, "error": "message" }` with HTTP 4xx/5xx.

---

## Core Concepts

| Concept | Description |
|---------|-------------|
| **Indicator Bank** | Master catalogue of humanitarian indicators. Each has a stable numeric `id`. |
| **Sector / Sub-sector** | Taxonomy grouping indicators (e.g. Health → First Aid). |
| **FDRS template** | Default form template id `21` — annual FDRS reporting. |
| **Period** | Reporting period label (e.g. `"Annual 2023"`, `"FY2024"`). |
| **FDRS overview** | Pre-aggregated numeric totals per country for one indicator. |

---

## Endpoints (public, no auth)

### Indicator Bank — `/api/v1`

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/indicator-bank` | Full catalogue with filters |
| GET | `/indicator-bank/<id>` | Single indicator (same object shape) |

### Public data — `/api/mobile/v1`

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/data/countrymap` | All countries (id, name, ISO codes, region) |
| GET | `/data/sectors-subsectors` | Sector tree with subsectors and logo URLs |
| GET | `/data/indicator-bank` | Paginated indicator list (same fields as v1) |
| GET | `/data/indicator-bank/<id>` | Single indicator |
| GET | `/data/periods` | Distinct reporting period names |
| GET | `/data/fdrs-overview` | Country-level totals for one indicator |
| GET | `/data/disaggregation-overview` | Global/regional sex/age breakdown |
| GET | `/data/resources` | Publications and resource library |

All mobile routes are rate-limited. See [reference.md](reference.md) for params
and response shapes.

---

## Workflow 1 — Explore the indicator catalogue

**Search by keyword:**
```
GET https://databank.ifrc.org/api/v1/indicator-bank?search=volunteers
```

**Filter by sector or type:**
```
GET https://databank.ifrc.org/api/v1/indicator-bank?sector=Health&type=Number
```

**Get full details for one indicator:**
```
GET https://databank.ifrc.org/api/v1/indicator-bank/42
```

Response field reference: [reference.md §1](reference.md).

---

## Workflow 2 — Get FDRS values for an indicator

**Step 1** — Find the indicator id (Workflow 1).

**Step 2** — List available periods:
```
GET https://databank.ifrc.org/api/mobile/v1/data/periods
GET https://databank.ifrc.org/api/mobile/v1/data/periods?template_id=21
```

**Step 3** — Fetch country totals:
```
GET https://databank.ifrc.org/api/mobile/v1/data/fdrs-overview
    ?indicator_bank_id=42
    &period_name=Annual%202023
```

Response `data.by_country` maps country id → total. Use `data.country_names`
and `data.country_iso2` for labels.

Optional: `template_id` (default `21`), `locale` for localized country names.

---

## Workflow 3 — Disaggregation breakdown (anonymous)

Global and regional sex/age aggregates — no per-country breakdown without login:
```
GET https://databank.ifrc.org/api/mobile/v1/data/disaggregation-overview
    ?indicator_bank_id=729
    &period_name=Annual%202023
```

Default indicator `729` is "people reached". Response includes `by_sex`, `by_age`
(each item has `category` + `value`), `by_region`, `trends`, and `total`.
`by_country` is empty for anonymous callers.

---

## Workflow 4 — Browse countries and sectors

**Countries:**
```
GET https://databank.ifrc.org/api/mobile/v1/data/countrymap
GET https://databank.ifrc.org/api/mobile/v1/data/countrymap?locale=fr
```

**Sectors (with subsectors and logo URLs):**
```
GET https://databank.ifrc.org/api/mobile/v1/data/sectors-subsectors
```

Sector logos are served from public `/api/v1/uploads/sectors/<filename>` URLs
embedded in the response.

---

## Workflow 5 — Publications and resources

```
GET https://databank.ifrc.org/api/mobile/v1/data/resources?page=1&per_page=20
GET https://databank.ifrc.org/api/mobile/v1/data/resources?search=FDRS&locale=en
GET https://databank.ifrc.org/api/mobile/v1/data/resources?grouped=true
```

---

## Tips

- Start with `/api/v1/indicator-bank` for metadata; use mobile `/data/fdrs-overview`
  for actual reported values.
- Always pass `period_name` to FDRS endpoints when comparing across years.
- FDRS template id defaults to `21`; pass `template_id` only for non-FDRS forms.
- `/api/v1/indicator-bank` returns the full filtered list in one response (cached
  5 min). Use mobile `/data/indicator-bank` with `page`/`per_page` for large
  paginated reads.
- Do not call `/api/v1/data`, `/api/v1/periods`, or `/api/v1/countrymap` — they
  require an API key.
