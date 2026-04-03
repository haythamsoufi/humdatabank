# UPR Domain Knowledge

> This document is the single source of truth for Unified Planning and Reporting (UPR) domain knowledge.
> It is used by developers as a reference **and** loaded at runtime by the AI agent when UPR context is active.
> Keep it concise and factual — every token counts when injected into an LLM context window.

---

## 1. What is UPR

UPR = **Unified Planning and Reporting**. It is **not** "Universal Periodic Review" on this platform.

UPR is an annual, results-based management process where IFRC member National Societies (NSs):

1. **Plan** — set objectives, targets, and funding requirements for the coming year(s).
2. **Report** — report progress against those targets at mid-year and end-of-year.

The process adopts a Federation-wide approach: it represents all international support the IFRC network provides to a National Society, centred on that NS's priorities.

### Reporting cycle

| Document | Period covered | Typical filename prefix |
|---|---|---|
| **Unified Plan** (Plan) | Multi-year (e.g. 2025–2027), submitted annually | `INP_YYYY_CountryName` |
| **Mid-year Report** (MYR) | January – June | `MYR_YYYY_CountryName` |
| **Annual Report** | January – December | `AR_YYYY_CountryName` |

Plans are often multi-year with a 3-year planning horizon (e.g. a 2025 plan covers 2025, 2026, 2027).

### Terminology — UPL vs UPR

- Document **titles and filenames** use **UPL** ("Unified Plan" / "UPL-2026"), not UPR.
- In user-facing text and agent answers, prefer **"Unified Plans and Reports"** or **"UPR documents"**.
- When searching documents via `list_documents`, use `"UPL-"` or `"Unified Plan"` as the query — searching `"UPR"` returns 0.

---

## 2. Document types and PDF structure

UPR documents are infographic-heavy PDFs. Standard OCR/table chunking is unreliable for them, so we use **visual chunking** — extracting structured JSON metadata from specific page regions.

### Pages and visual blocks

The key visuals are concentrated on **pages 1–5** of each PDF:

| Visual block | Block type key | Typical page(s) | Content |
|---|---|---|---|
| **IN SUPPORT OF \<NS\>** KPI cards | `in_support_kpis` | 1–3 | 4 KPI cards: branches, local_units, volunteers, staff |
| **People Reached** / **People To Be Reached** | `people_reached` / `people_to_be_reached` | 1–3 | Breakdown by Strategic Priority category |
| **Financial Overview** | `financial_overview` | 2–4 | IFRC network funding requirement, funding, expenditure (CHF) |
| **Funding Requirements** | `funding_requirements` | 3–5 | Multi-year funding totals and breakdowns by source, IFRC breakdown, PNS bilateral |
| **Hazards** | `hazards` | 3–5 | List of hazard types (Conflict, Earthquakes, etc.) |
| **PNS Bilateral Support** | `pns_bilateral_support` | 3–5 | Table of PNS names and funding requirement per NS |

### People Reached / To Be Reached categories

These map 1:1 to IFRC Strategic Priorities:

- Emergency Operations (cross-cutting)
- Climate and environment (SP1)
- Disasters and crises (SP2)
- Health and wellbeing (SP3)
- Migration and displacement (SP4)
- Values, power and inclusion (SP5)

### KPI cards — Indicator Bank mapping

| KPI | Indicator Bank ID |
|---|---|
| volunteers | 724 |
| staff | 727 |
| branches | 1117 |
| local_units | 723 |

---

## 3. Web form structure (Databank entry)

When data is entered through the Databank web forms (not PDFs), the structure differs between Plans and Reports.

### Unified Country Plan (single page form)

1. **NS Key Figures** — Volunteers, Staff, Branches, Local Units
2. **People to be reached** — by Strategic Priority (longer-term + Emergency Appeals)
3. **Planned bilateral support** — PNS matrix by SP/EF
4. **Funding requirements (CHF)** — 3-year outlook, broken into HNS/IFRC Secretariat and PNS sub-sections
5. **Comments**

### Unified Country Report (5-page form)

| Page | Content |
|---|---|
| **P1 — Overall Action Indicators** | NS Data (4 KPIs) + core indicators by SP/EF + optional additional indicators |
| **P2 — Emergency Appeals Indicators** | Active appeals from GO platform, per-appeal indicator selection |
| **P3 — Funding** | NS Total Funding, NS Total Expenditure, optional SP/EF breakdown (all CHF) |
| **P4 — Bilateral Support** | Actual bilateral support received from PNSs |
| **P5 — Comments** | Free-text comments for validation context |

### Core indicators on Page 1

Organized by Strategic Priority (SP) and Enabling Function (EF):

- **Cross Cutting**: people reached with long-term services; emergency response and early recovery
- **SP1 Climate & environment**: climate risks, heatwave, environmental campaigns, climate strategies
- **SP2 Disasters & crises**: DRR, emergency response, cash/vouchers %, livelihoods, shelter
- **SP3 Health & wellbeing**: health services, WASH, first aid, blood donation, MHPSS, immunization
- **SP4 Migration & displacement**: migrants/displaced reached, HSPs, advocacy, data collection
- **SP5 Values, power & inclusion**: education, PGI, CEA, information/feedback
- **EF1 Strategic coordination**: government-led and interagency platforms
- **EF2 NS development**: auxiliary role, NS dev plan, youth, volunteer coverage
- **EF3 Humanitarian diplomacy**: IFRC campaigns, domestic advocacy
- **EF4 Accountability & agility**: PSEA policy/action plan, integrity, digital transformation, data management

---

## 4. Metadata schema — `extra_metadata["upr"]`

When a UPR PDF is processed through visual chunking, each extracted block is stored as an `AIDocumentChunk` with `chunk_type = "upr_visual"` and structured data in `extra_metadata["upr"]`.

### Common envelope

Every block has:

```json
{
  "block": "<block_type>",
  "page_number": 3,
  "extraction": "<method_version>",
  "confidence": 0.9,
  "upr_context": {
    "document_year": 2025,
    "year": 2025,
    "doc_type": "plan",
    "covered_years": [2025, 2026, 2027],
    "planning_horizon_years": [2025, 2026, 2027]
  }
}
```

- `extraction` encodes the method (e.g. `"fixed_4col_v1"`, `"vision_gpt4v"`, `"layout_v1"`, `"fullpage_multi_year_plan_2025"`)
- `confidence` is 0.0–1.0; values ≥ 0.9 are considered reliable
- `doc_type`: `"plan"` | `"midyear_report"` | `"annual_report"` | `"unknown"`

### Block-specific payloads

#### `in_support_kpis`

```json
{
  "block": "in_support_kpis",
  "society": "Afghan Red Crescent Society",
  "kpis": {
    "branches": "34",
    "local_units": "329",
    "volunteers": "26,000",
    "staff": "4,000"
  }
}
```

Values are strings (may contain commas, magnitude suffixes like `1.4M`). Downstream parsing handles normalization.

#### `people_reached` / `people_to_be_reached`

```json
{
  "block": "people_reached",
  "people_reached": {
    "emergency_operations": "150,000",
    "climate_and_environment": "50,000",
    "disasters_and_crises": "200,000",
    "health_and_wellbeing": "100,000",
    "migration_and_displacement": "30,000",
    "values_power_and_inclusion": "25,000"
  }
}
```

#### `financial_overview`

```json
{
  "block": "financial_overview",
  "financial_overview": {
    "ifrc_network": {
      "funding_requirement": "10,000,000",
      "funding": "8,000,000",
      "expenditure": "7,500,000"
    },
    "ifrc_secretariat": {
      "longer_term": { "funding_requirement": "...", "funding": "...", "expenditure": "..." },
      "emergency_operations": { "funding_requirement": "...", "funding": "...", "expenditure": "..." }
    },
    "participating_national_societies": { "funding_requirement": "...", "funding": "...", "expenditure": "..." },
    "hns_other_funding_sources": { "funding_requirement": "...", "funding": "...", "expenditure": "..." }
  }
}
```

#### `funding_requirements`

```json
{
  "block": "funding_requirements",
  "funding_requirements": {
    "currency": "CHF",
    "totals_by_year": { "2025": "5,000,000", "2026": "4,500,000", "2027": "4,000,000" },
    "breakdown_by_year": {
      "2025": {
        "through_ifrc": "2,000,000",
        "through_participating_national_societies": "1,500,000",
        "host_national_society": "1,500,000"
      }
    },
    "ifrc_breakdown_by_year": {
      "2025": {
        "ongoing_emergency_operations": "500,000",
        "strategic_priorities": {
          "climate_and_environment": "300,000",
          "disasters_and_crises": "400,000",
          "health_and_wellbeing": "350,000",
          "migration_and_displacement": "250,000",
          "values_power_and_inclusion": "200,000"
        },
        "enabling_functions": "100,000"
      }
    },
    "participating_national_societies": {
      "bilateral": ["Swedish Red Cross", "Norwegian Red Cross"],
      "multilateral": ["IFRC"]
    }
  }
}
```

#### `hazards`

```json
{
  "block": "hazards",
  "hazards": ["Conflict", "Earthquakes", "Displacement", "Wildfires", "Heatwaves"]
}
```

#### `pns_bilateral_support`

```json
{
  "block": "pns_bilateral_support",
  "pns_bilateral_support": {
    "year": "2025",
    "currency": "CHF",
    "total_funding_requirement": "3,000,000",
    "rows": [
      { "national_society": "Swedish Red Cross", "funding_requirement": "500,000" },
      { "national_society": "Norwegian Red Cross", "funding_requirement": "400,000" }
    ]
  }
}
```

---

## 5. Extraction methods

### Layout-based extraction (default, no vision LLM)

- Parses OCR text from `pages[i]["text"]` using regex patterns and positional heuristics.
- Methods: `fixed_4col_v1` (KPIs), `regex_v1`/`regex_v2` (people reached), `panel_v1`/`panel_v2` (financial overview), `fullpage_multi_year_plan_2025` (funding requirements).
- Scoped to first 3 pages for most blocks; up to 5 pages for funding requirements.
- Confidence typically 0.8–0.9 depending on OCR quality.

### Vision LLM extraction (optional, requires `AI_UPR_VISION_KPI_ENABLED=True`)

- Creates a cropped top-of-page PNG at configured DPI.
- Sends image to a vision model (e.g. GPT-4V) with a structured prompt.
- Returns JSON: `{"branches": "...", "local_units": "...", "volunteers": "...", "staff": "..."}`.
- Method tag: `"vision_gpt4v"` (or model-specific).
- Confidence typically 0.95+ when successful.

### Extraction string format in data retrieval

The `extraction` field is parsed for year and report type:

- Pattern: `<method>` optionally followed by year/type tokens.
- `_parse_upr_extraction_meta(extraction_str)` returns `{"year": int, "report_type": str}`.
- Report types: `"plan"`, `"midyear"`, `"annual"`, `"unknown"`.

---

## 6. Data storage and retrieval

### Where UPR data lives in the database

| Table | Column | What |
|---|---|---|
| `ai_document_chunks` | `extra_metadata` (JSON) | `extra_metadata["upr"]` holds the block payloads above |
| `ai_document_chunks` | `chunk_type` | `"upr_visual"` for visual blocks |
| `ai_document_chunks` | `content` | Embedding-friendly text rendering of the block |
| `ai_documents` | `title`, `filename` | Used to infer country, year, doc_type |

### SQL query patterns (data_retrieval.py)

- **Single country KPI**: filters `extra_metadata` JSON for `block = "in_support_kpis"`, matches country via document → country association, extracts `kpis.<metric>`.
- **Time series**: groups by document year, picks best confidence per year, returns `[{year, value, source}]`.
- **All countries**: scans all `in_support_kpis` blocks, joins to country table, deduplicates by preferring highest confidence per country.

### FDRS vs UPR priority

- **FDRS (Indicator Bank)** is the primary/authoritative source for KPI values (volunteers, staff, branches, local_units).
- UPR document-extracted values are secondary — used to **fill gaps** for countries/years where FDRS has no data.
- When both sources have data for the same year: prefer FDRS (especially if submitted/approved).
- For "from UPR/documents only" requests: use only UPR tools.
- For "databank only" requests: use only FDRS tools, exclude UPR.

---

## 7. AI tools for UPR

| Tool | Purpose | Key params |
|---|---|---|
| `get_upr_kpi_value` | Single country, single metric from document metadata | `country_identifier`, `metric` |
| `get_upr_kpi_timeseries` | Year-over-year series for one country | `country_identifier`, `metric` |
| `get_upr_kpi_values_for_all_countries` | Bulk: one metric across all countries | `metric` |
| `analyze_unified_plans_focus_areas` | Classify which plans mention a theme/focus area | `areas[]`, `limit` |

### Metrics accepted by KPI tools

`branches`, `local_units`, `volunteers`, `staff` — best-effort normalization is applied.

### Focus area analysis

`analyze_unified_plans_focus_areas` works for:
- Built-in areas: `cash`, `cea`, `livelihoods`, `social_protection`
- Extended: `migration`, `displacement`, `climate`, `mhpss`, `pgi`, `health`, `disaster_risk_reduction`
- Any free-text label in `snake_case` (auto-matched via keyword patterns)

---

## 8. Configuration flags

| Env var / config key | Default | Purpose |
|---|---|---|
| `AI_UPR_VISUAL_CHUNKING_ENABLED` | `True` | Master switch for visual block extraction during PDF processing |
| `AI_UPR_LAYOUT_KPI_ENABLED` | `True` | Enable layout-based (regex/OCR) KPI extraction |
| `AI_UPR_VISION_KPI_ENABLED` | `False` | Enable vision LLM KPI extraction (requires vision model) |
| `AI_UPR_VISION_MAX_PAGES` | `8` | Max pages to scan with vision model |
| `AI_UPR_VISION_DPI` | `150` | DPI for page-to-image conversion |
| `AI_UPR_VISION_CLIP_TOP_FRAC` | `0.0` | Fraction of page top to crop for vision (0.0 = no crop) |
| `AI_UPR_VISION_MODEL` | `""` | Specific vision model override (empty = use default) |

---

## 9. Activation gate

UPR tools, prompts, and instructions are only active when `is_upr_active()` returns `True`.

Decision order:
1. `flask.g.ai_sources_cfg["upr_documents"]` — explicit user toggle from chat UI.
2. `True` when `sources_cfg` is `None` (backward compat / no explicit selection).
3. `True` outside Flask request context (scripts, CLI, tests).

When inactive, UPR tool definitions are excluded from the tool list, UPR prompt sections are not injected, and the gap-fill reminder is suppressed.

---

## 10. Query detection

`query_prefers_upr_documents(query)` returns `True` when a query explicitly targets UPR/UPL/Unified Plan documents but does **not** mention Annual Reports or MYRs.

Positive triggers: `unified plan`, `upl-YYYY`, `upl`, `upr`, `up plan`.
Negative overrides: `annual report`, `semi-annual report`, `midyear report`, `ar`, `myr`.

This narrows document search scope from (system + UPR) to (UPR only) — it never widens access.

---

## 11. Key financial definitions

| Term | Definition |
|---|---|
| **Funding requirements** | Total financial resources needed for operations, programmes, appeals (annualized, including opening balance, secured and expected funding). |
| **HNS other funding sources** | Host NS funding from sources outside the IFRC network. |
| **Bilateral support** | Direct cooperation between two NSs without going through IFRC. |

Currency is always **CHF** unless otherwise stated.

---

## 12. Known gaps and limitations

- **No formal JSON Schema** for `extra_metadata["upr"]` — the schema is implicitly defined by extractor code and this document.
- **Deterministic answering** currently supports `in_support_kpis` and `people_reached`/`people_to_be_reached` blocks; `financial_overview`, `funding_requirements`, `hazards`, and `pns_bilateral_support` fall back to text search.
- **Vision extraction** is optional and disabled by default; layout-based extraction is the primary path.
- **Year inference** is best-effort from filename/title; multi-year plans can be ambiguous.
- UPR started in 2023 — documents before that year are not expected.
