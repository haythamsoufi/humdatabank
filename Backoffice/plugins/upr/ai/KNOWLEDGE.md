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

- `extraction` encodes the method that produced the block (e.g. `"label_proximity_v2"`, `"vision_openai_v1"`, `"funding_requirements_fullpage_v1"`) — see section 5 for the full, per-block-type list kept in sync with the extractor code
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

Every extractor lives in `visual_chunking.py` and tags its output with an `extraction`
value on the block. Methods for the same block type are tried in order (most reliable /
most specific first) and the first one that produces a plausible result wins — the tag
tells you which heuristic actually fired for a given block, which matters when debugging
a wrong or missing value. **Keep this list in sync with the code** — grep the file for
`"extraction":` when in doubt, since this is a common source of doc drift.

### `in_support_kpis` (`extract_in_support_kpis`) — tried in this order

| Tag | Confidence | Approach |
|---|---|---|
| `vision_openai_v1` | 0.92 | Vision LLM on a cropped page image (see below). Only tried when `AI_UPR_VISION_KPI_ENABLED=true` and a clip render is available. |
| `layout_words_v1` | 0.97 | Maps `pages[i]["words"]` (bounding boxes) to labels by x-position proximity. Only tried when `AI_UPR_LAYOUT_KPI_ENABLED=true` and word boxes are available. |
| `kpi_cards_v3` | 0.94 | OCR text: finds 4 numbers near "national society" occurrences close to each label. |
| `kpi_cluster_v3` | 0.93 | OCR text fallback: picks the best 4-number cluster on a line when OCR linearizes all KPI numbers into one row. |
| `label_proximity_v2` | 0.90 | **Default/most common path.** Nearest number above/near each of the 4 labels, robust to Planning vs MYR label ordering. |
| `label_proximity_partial_v2` | 0.75 | Same as above but only 3 of 4 labels matched — kept as better-than-nothing. |
| `fixed_4col_v1` | 0.85 | Last resort: finds one line with exactly 4 numbers and maps them by label order found in text (or a default order). |

Vision and word-layout extraction are both **off by default** (see section 8) — layout-based
OCR/regex heuristics (`label_proximity_v2` and friends) are what actually fires for most
documents today.

### `people_reached` / `people_to_be_reached` (`extract_people_reached`)

- Single method, tag `fixed_6col_v1`, confidence 0.9.
- Finds a 6-number row below the "PEOPLE (TO BE) REACHED" header (or accumulates numbers
  across two adjacent OCR lines), and maps them in fixed category order. Requires all 6
  category keywords (emergency/climate/disasters/health/migration/values) to appear in
  the window, else the page is skipped.

### `financial_overview` (`extract_financial_overview`)

- Single method, tag `labeled_fields_v2`, confidence 0.72 (lowest of all block types —
  this panel's OCR layout is the noisiest).
- Parses IFRC network / IFRC Secretariat (longer-term + emergency ops) / PNS / HNS-other
  sub-panels by section header + "funding requirement"/"funding"/"expenditure" label proximity.

### `funding_requirements` (`extract_funding_requirements`)

| Tag | Confidence | Approach |
|---|---|---|
| `funding_requirements_fullpage_v1` | 0.85–0.86 | Full-page multi-column layout (plans 2025+): year columns each with Total, funding sources, IFRC breakdown. |
| `funding_requirements_v1` | 0.75–0.86 | Current Planning panel layout; scales up with more years found (≥2 years → 0.82) and a parsed source breakdown (→ 0.86). |
| `funding_requirements_single_year_v0` | 0.68 | OCR text has a single "Funding Requirement CHF X" callout with no year columns; amount is attached to the inferred document year. |
| `funding_requirements_single_year_words_v0` | 0.66 | Weakest path: OCR text is empty/unusable, so the single amount is recovered from `pages[i]["words"]` instead. |

The optional "Participating National Societies" bilateral/multilateral name list and the
PNS funding-source amount share parsing logic with `document_answering.py` via
`plugins/upr/excel/pns_parsing.py` (see section 4's `funding_requirements` payload).

### `hazards` (`extract_hazards`)

- Single method, tag `hazards_v1`, confidence 0.85. Matches known hazard keywords
  (Conflict, Earthquakes, Displacement, Wildfires, Heatwaves, …) under a "Hazards" header.

### `pns_bilateral_support` (`extract_pns_bilateral_support`)

- Single method, tag `pns_bilateral_support_v1`, confidence 0.8. Parses the
  "Participating National Societies bilateral support for YYYY" table (older country-plan
  layout) into `{national_society, funding_requirement}` rows plus a total.

### Vision LLM extraction detail (optional, requires `AI_UPR_VISION_KPI_ENABLED=true`)

- Creates a cropped top-of-page PNG at the configured DPI (`AI_UPR_VISION_DPI`,
  `AI_UPR_VISION_CLIP_TOP_FRAC`).
- Sends the image to a vision model (`AI_UPR_VISION_MODEL`, default `gpt-4o-mini`) with a
  structured prompt; requires `OPENAI_API_KEY`.
- Returns JSON: `{"branches": "...", "local_units": "...", "volunteers": "...", "staff": "..."}`.
- Tag: `vision_openai_v1`. See the `in_support_kpis` table above for confidence.

### Year / report-type resolution in data retrieval

`year` is **not** encoded in the `extraction` tag string — those tags are bare method names
(e.g. `"label_proximity_v2"`), not `key=value` pairs. Both KPI lookup functions resolve year
via the shared `_resolve_upr_block_year(upr, doc)` helper (`data_retrieval.py`):

1. A 4-digit token in the document filename (max if several, e.g. a `"INP_2025_2027_..."`
   range) — matched with digit-boundary lookarounds (`(?<!\d)(19\d{2}|20\d{2})(?!\d)`), **not**
   `\b`, since `_` is a word character and `\b` alone would silently miss the common
   underscore-delimited naming convention (`INP_2023_Foo.pdf`). The same fix is applied
   independently in `visual_chunking.py`'s `_years_from()` and `validation.py`'s `_YEAR_RE`
   (used for `upr_document_label`) — if you touch year-from-filename parsing, keep all three
   consistent.
2. `upr_context.year`.
3. A `year=` token inside `extraction` (defensive fallback only — no current extractor emits
   that format, so this branch is effectively dead today).

- `get_upr_kpi_timeseries`: uses `_resolve_upr_block_year`, then falls back to
  `doc.processed_at`/`created_at` if still unresolved (a time-series point needs *some* year
  to bucket by). `doc_type`/report-type comes from `upr_context.doc_type` or a filename
  heuristic (`_ar_`/annual → `annual_report`, `_myr_`/mid → `midyear_report`, else `plan`).
- `get_upr_kpi_value`: ranks candidates by `(prefer_year match, confidence, recency)`, where
  the year used for the `prefer_year` match is from `_resolve_upr_block_year` (fixed — this
  used to go through `_parse_upr_extraction_meta(extraction)` instead, which only recognizes
  `pe=`/`ype=`/`year=` tokens that no extractor emits, so `prefer_year` was silently a no-op).
  The candidate's surfaced `report_type` field (`source.report_type` in the response) is
  **still** sourced from `_parse_upr_extraction_meta(extraction).get("report_type")` and is
  therefore still effectively always `None` in practice — a smaller, separate gap from the
  `prefer_year` one (see section 12). It isn't part of the ranking key, so it doesn't affect
  which candidate wins, only the informational value returned to the caller.
- `prefer_year` reaches the chat AI too: the `get_upr_kpi_value` tool spec (`tool_specs.py`)
  exposes an optional integer `year` argument, and the registry wrapper
  (`app/services/ai/tools/registry.py`) forwards it as `prefer_year`. Before this it was only
  reachable from the internal `retrieve_upr_kpi_reference()` caller (form-suggestions) — chat
  users asking about a specific year had no way to influence ranking at all.

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
| `get_upr_kpi_value` | Single country, single metric from document metadata | `country_identifier`, `metric`, optional `year` |
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

Read directly from `current_app.config` / `os.environ` at chunking time (not merged from
the AI tab in System Configuration). Seed them in `env.example` / your `.env` if you need a
non-default value. **Defaults below are the code's actual fallback values** — verify against
`visual_chunking.py`'s `_cfg(...)` calls and `app/services/ai/documents/processor.py` before
trusting this table blindly; it has drifted from the code before.

| Env var / config key | Default | Purpose |
|---|---|---|
| `AI_UPR_VISUAL_CHUNKING_ENABLED` | `true` | Master switch for visual block extraction during PDF processing (`chunking.py`) |
| `AI_UPR_LAYOUT_KPI_ENABLED` | `false` | Enable the `layout_words_v1` word-bbox KPI fallback (off by default — needs page word boxes) |
| `AI_UPR_VISION_KPI_ENABLED` | `false` | Enable the `vision_openai_v1` vision-LLM KPI fallback (requires `OPENAI_API_KEY`) |
| `AI_UPR_VISION_MODEL` | `gpt-4o-mini` | Vision model used by `AI_UPR_VISION_KPI_ENABLED` |
| `AI_UPR_VISION_MAX_PAGES` | `1` | Max pages rendered to images for vision KPI extraction (`processor.py`) |
| `AI_UPR_VISION_DPI` | `160` | DPI for page-to-image conversion for vision extraction (`processor.py`) |
| `AI_UPR_VISION_CLIP_TOP_FRAC` | `0.42` | Fraction of page height cropped from the top before the vision crop (0.0 = no crop; `processor.py`) |

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
- **`get_upr_kpi_value(..., prefer_year=...)` `report_type` is not resolved** — the winning candidate's `source.report_type` in the response is sourced from `_parse_upr_extraction_meta(extraction)`, which parses `pe=`/`ype=`/`year=` tokens that no current extractor emits (see section 5), so it is effectively always `None`. This is purely informational (not part of the ranking key, unlike `year` — see next point), so it doesn't affect *which* candidate is returned, only a field on it. Fixing it would mean deriving `report_type` the same filename/`upr_context.doc_type` way `get_upr_kpi_timeseries` already does, via a shared helper.
- ~~`get_upr_kpi_value(..., prefer_year=...)` does not actually prefer the requested year~~ — **fixed**: year for ranking now comes from the shared `_resolve_upr_block_year` helper (filename / `upr_context.year`), not from `_parse_upr_extraction_meta`.
- UPR started in 2023 — documents before that year are not expected.

---

## 13. Form-data AI validation (Unified Plan/Report assignments)

When staff run **AI validation summary** on a Unified Country Plan (template 24) or Unified Country Report (template 33), the UPR plugin injects extra instructions and structured visual-block evidence.

Implementation: `plugins/upr/ai/form_validation.py` + `get_upr_formdata_validation_prompt()` in `prompts.py`. Core service: `AIFormDataValidationService`.

### What is injected

- Domain rules: plan vs report, 3-year funding horizon, HNS / IFRC Secretariat / PNS, Strategic Priorities / Enabling Functions, CHF.
- Evidence priority: Unified Plan/Report visual blocks and PDFs first; historical submissions second; Annual Reports / Strategic Plans as **context only** (they are not a same-year SP×actor plan matrix).
- Field kinds: people to be reached, bilateral PNS support, funding requirements, NS KPI cards, comments.
- Comments are **not** numeric indicators — they are not compared to historical numbers or document totals.
- **Matrix reading** (`plugins/upr/ai/matrix_reading.py`): decodes form cells into actor × programme (Resilience/Response) × Strategic Priority × year, with totals and like-for-like notes against PDF visual blocks. The arithmetic sum of cells is **not** treated as one indicator. The reading is a decode of the form (not independent confirmation). People-to-be-reached / people-reached cells are always **people targets or actuals** (including compact keys such as `2027_SP1`), even when the numbers are small; tiny counts are implausible people figures, not a different unit.
- **Historical matrices**: the same field on prior submitted/approved assignments is decoded and compared cell-by-cell (matched via `stable_key` / template + label, including across UPR template ids, when `form_item_id` differs across years). A current people grid of 0–99 versus a prior people grid of thousands or millions is a **unit/scale change** (discrepancy) — never “good” just because the current grid is internally consistent or matches its own decode. Bilateral ticks are compared as PNS names, not CHF.

### Visual blocks used as structured evidence

| Form field | Blocks retrieved |
|---|---|
| People to be reached | `people_to_be_reached`, `people_reached` |
| Bilateral support | `pns_bilateral_support`, `funding_requirements` |
| Funding requirements | `funding_requirements`, `financial_overview` |
| NS key figures | `in_support_kpis` (existing KPI path) |

Enable **UPR documents** in the validation-sources picker so API-imported Unified Plan PDFs are searched (`is_api_import=true`). The UI default includes this source.

---

## 14. Assignment review (Validation summary)

The on-form **Validation summary** and the **Validation details** page must review the assignment as a whole — not only count per-field verdicts. Implementation: `plugins/upr/ai/assignment_review.py` (deterministic pack) + `get_upr_assignment_review_prompt()` + `app/services/ai/validation/assignment_review.py` (LLM briefing).

### Policy (always inject into field validation AND the assignment summary)

1. **People to be reached — longer term (item 954)**  
   Cells are **people targets**. Tiny integers (0–99) versus a prior assignment in the thousands or millions is a **flag**. Do not treat a self-consistent 0/1/5 grid as valid “programme flags”.

2. **People to be reached — emergencies (item 960)**  
   Rows are added from the country GO emergency-operations list. If an emergency is available and the focal point did not add it, or added it with no people value, **flag**.

3. **National Society key figures**  
   If the section is completely empty, **flag** the assignment (not “nothing to validate”).

4. **Funding Requirements for the assignment year (item 967) — IFRC Secretariat**  
   The IFRC Secretariat row must have a value in every static column (SP1–SP5, EFs), including selectable emergency-appeal columns once chosen.  
   - Emergency **selected** (`col_header|EA1` / `EA2` / `EA3`) and IFRC Secretariat cell empty → **flag**.  
   - No emergency selected, but one or more operations are available in the list → **highlight** (focal point did not select it).

5. **Comments (item 956)**  
   Free-text from the reporting country; may be a language other than English. The assignment review **must** read it, translate the meaning into English, and apply caveats to other fields (why an emergency was omitted, why people figures changed, why a year is blank).

### Gotcha: `[variable]` placeholders in FormItem labels

Some item labels carry template placeholders such as `[assignment_period]` (see
`VariableResolutionService`) that the entry form resolves at render time. `build_upr_assignment_review_pack()`
reads `FormItem.label` directly, so every audit function that builds an end-user-facing finding `label`
must resolve it too — call `_item_label(item, resolved_variables, variable_configs)`, not `_item_label(item)`
alone, or the literal bracket text (e.g. `"Emergency Appeals in [assignment_period]"`) leaks into the numbered
issues list. `resolved_variables`/`variable_configs` are computed once per pack via
`VariableResolutionService.resolve_for_assignment_display(aes)` and threaded into every `audit_*` call.

### Gotcha: `list_available_emergencies()` must read *per-column* config, not just the matrix-level one

A matrix can source `emergency_operations` rows/options two structurally different ways, and each stores its
filters in a different place:

- **Row-mode/hybrid** list-library rows (e.g. item 960, "Emergency Appeals in `[assignment_period]`" under
  people-to-be-reached): one shared `matrix_config.plugin_config`.
- ***Selectable header* columns** (e.g. item 967's `EA1`/`EA2`/`EA3` funding columns): each column has its own
  `header_plugin_config`, and a matrix built entirely of selectable EA columns commonly has **no top-level
  `plugin_config` key at all**. Columns can legitimately disagree with each other (one EA slot pinned to the
  current assignment period, another using a static cutoff) — see
  `app/static/js/forms/modules/matrix/selectable-headers.js`, which resolves each column's config as
  `columnDef?.header_plugin_config || matrix?.config?.plugin_config || null` before calling the live
  "search options" endpoint (`/forms/matrix/search-rows` → `get_emergency_operations_options_handler`).

`list_available_emergencies()` in `plugins/upr/ai/assignment_review.py` mirrors that exact fallback via
`_emops_config_sources()` and unions the results (deduped by code) across every source. Reading only the
matrix-level `plugin_config` (the old behaviour) meant a selectable-header-only matrix like item 967 fell
through to an **empty** config, which `_normalize_emops_config({})` turns into almost no filtering
(`operation_types=['All']`, closed operations included, no date cutoff) — the opposite failure mode from "no
options": it silently invented availability. That produced a real false positive on assignment 4301 ("No
emergency appeal is selected for funding, but 2 operation(s) are available…") when every one of that item's
real EA1/EA2/EA3 dropdowns legitimately resolved to zero options once their own (stricter) filters were
applied. Regression tests: `TestListAvailableEmergencies` in `tests/unit/test_plugins/test_upr_ai.py`.

### Division of labour: deterministic pack vs LLM (avoid repeating the same content 3x)

`overview_figures`, `whats_good`, `whats_not` and `comment_note` are built **once**, deterministically, by
`build_upr_assignment_review_pack()` / `_fallback_review()` — never regenerated by the LLM. They are cheap
(no LLM call needed to produce them), reliable, and `whats_not` carries the real `form_item_id` so the UI
can render a numbered, clickable "Needs attention" list that scrolls to the right field.

**`overview_figures` only shows a tile for a check that is fully "ok"** — gated on the `status` each
`pack["figures"][...]` sub-dict carries (`_with_status()`, set once from the same finding(s) that also feed
`flags`/`highlights`/`ok`, so the pass/fail decision is never re-derived a second time and can't drift out of
sync). A flagged or highlighted check is deliberately given **no** tile: it already has a full, friendly
sentence in the numbered "Needs attention" list a few lines below, and a bare "0 of 4 completed"-style number
restating that same issue is exactly the unhelpful-figure pattern (`"max cell 5, 8 non-zero of 15"`) this
briefing was built to get away from. The only reason a tile exists at all is that "In good shape" is collapsed
by default — without a tile, a passing check's sentence would be invisible until clicked.

The assignment-level LLM (`get_upr_assignment_review_prompt()` in `prompts.py`, only called when an
`OPENAI_API_KEY` is configured and the pack is non-empty) is asked for **only** two strings on top of that:

- `headline` — one prioritised sentence (in the LLM's own words, not copied from a finding).
- `narrative` — 0–3 short sentences of genuinely new synthesis: which issue to fix first and why, whether
  findings compound, whether the item-956 comment explains/excuses a gap elsewhere. Empty string if there is
  nothing to add beyond the lists.

The LLM is explicitly told **not** to restate `overview_figures` / `whats_good` / `whats_not` — that content
already exists and would otherwise be shown to the user three times (headline blob, narrative paragraph, and
the lists themselves). If the LLM is unavailable or fails, `generate_assignment_review()` falls back to a
short heuristic headline (issue count + top label, e.g. "2 issues need attention, starting with National
Society key figures.") and an empty narrative — never a concatenation of the finding texts.

### Same split also powers real (not just canned) loading-animation stages

`generate_assignment_review()` in `app/services/ai/validation/assignment_review.py` is a thin wrapper around
two phases — `build_review_pack_and_fallback()` (the deterministic pack above) then `finish_review_with_llm()`
(the headline/narrative LLM call) — kept as separate public functions specifically so
`forms_validation_summary.validation_summary_overview_stream` (SSE) can `yield` a real "stage" event
*immediately before* each phase starts, instead of a client-side timer guessing what the backend might be
doing. The on-form banner (`validation-summary-banner.js`) drives its loading phrase from these real events
and only falls back to gently cycling canned text if a stage genuinely stalls (e.g. a slow LLM call) — see
that route's docstring for the exact event sequence (`reading` → `figures` → `summary` only if a pack/LLM
call will really happen → `result`). The plain, non-streamed `validation_summary_overview` JSON endpoint is
kept side-by-side (same helpers, same output shape) for any caller that just wants one response.

