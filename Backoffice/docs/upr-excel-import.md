# UPR Excel Import — Design, Implementation & Handover Guide

> **Status:** Active / In progress  
> **Last updated:** June 2026  
> **Primary files:** `Backoffice/scripts/import_upr_excel_data.py` · `Backoffice/app/services/upr_excel_import_service.py` · `Backoffice/app/routes/admin/upr_excel_import.py` · `Backoffice/app/templates/admin/templates/upr_excel_import.html`

---

## 1. Purpose

Sync planning data from **UPR Master.xlsx** (sheet `UPR Data`) into form submissions in the Backoffice database. The workbook is the authoritative source for countries' Unified Planning & Reporting data across ~109 k rows and 192 countries.

### Templates in scope (planning rounds)

| Template ID | Name | Sections imported |
|-------------|------|-------------------|
| **24** | Unified Country Plan | NS Data, Funding (country-reported), Reach, Support, Comments |
| **22** | Annual Planning – International Bilateral Support | Funding (PNS-reported), Staff |

Reporting templates (e.g. template **25**) are **not yet implemented** — see §9.

---

## 2. Excel file structure

- **Sheet:** `UPR Data`
- **Header row:** row 3 (0-based index 2 in openpyxl)
- Approximately 109 k data rows; each row represents one indicator value for one country/round/section

### Key columns

| Column | Purpose |
|--------|---------|
| `ISO3` | Host country code |
| `Country` | Country name |
| `Round` | Planning round code (`P23`–`P26`) |
| `Year` | Calendar year the value applies to |
| `Section` | Logical section: `NS Data`, `Funding`, `Reach`, `Support`, `Comments`, `Staff` |
| `Entity` | Who owns the value: `HNS`, `IFRC Secretariat`, `PNS`, `All-PNS` |
| `NS` | Name of the specific National Society (critical for PNS rows) |
| `Source` | Reporting source: `Country Data`, `PNS Data`, `Mix Data` |
| `Area` | SP1–SP5, EFs, EA1–EA3, EAs, or Total |
| `Attribute` | Row type: `SP Breakdown`, `Total`, `SubTotal` |
| `Indicator` | Indicator label |
| `indicatorId` | Numeric indicator bank ID |
| `ValueNum` | Numeric value (not used for Funding or Comments) |
| `Country Value` | Value as reported by the country (Funding) |
| `PNS Value` | Value as self-reported by the PNS (Funding) |
| `Value` / `UPR Value` | Free-text value (Comments) |
| `EA Code` | GO appeal code (e.g. `MDRAF019`) for Emergency Appeals rows |

### Round → period mapping

`P26` → assignment `period_name = "2026"` via `2000 + int(round[1:])`.

---

## 3. Architecture overview

```
UPR Master.xlsx
      │
      ▼
load_upr_data_sheet()          ← reads sheet, skips rows 1-2, returns list[dict]
      │
      ▼
build_import_context()         ← queries DB: assignments, items, NS index, country_id, GO ops config
      │
      ▼
transform_to_import_rows()     ← maps Excel rows → normalised form_data rows (same schema as FDRS import)
      │
      ▼
upsert_form_data_rows()        ← shared helper in import_fdrs_form_data.py; batch INSERT/UPDATE form_data
```

The script can be run:
- **CLI:** `python scripts/import_upr_excel_data.py --input "UPR Master.xlsx" --rounds P26 --templates 24,22 --dry-run`
- **UI wizard:** `/admin/templates/upr-excel-import/` (4-step wizard, async background job)

---

## 4. Template profiles (`UPR_TEMPLATE_PROFILES`)

Each template is registered with the sections it handles and the round prefixes it accepts:

```python
UPR_TEMPLATE_PROFILES = {
    24: {"name": "Unified Country Plan",
         "round_prefixes": ("P",),
         "sections": frozenset({"Reach", "NS Data", "Funding", "Comments", "Support"})},
    22: {"name": "Annual Planning - International Bilateral Support",
         "round_prefixes": ("P",),
         "sections": frozenset({"Staff"})},
}
```

Adding a new template means adding an entry here and a handler block in `transform_to_import_rows`.

---

## 5. Import context (`UprImportContext`)

Built once per import run by `build_import_context()`. Caches all DB lookups so the main loop makes zero extra queries.

| Field | Contents |
|-------|---------|
| `assignment_by_template` | `{template_id: {(period, iso3): aes_id}}` — per-template, no key collisions |
| `assignment_by_period_iso` | Same as `assignment_by_template[24]` — backwards-compat shortcut for non-Funding sections |
| `items_by_bank_id` | `{template_id: {indicator_bank_id: form_item_id}}` |
| `item_ids_by_label` | `{template_id: {label_lower: form_item_id}}` |
| `ns_name_to_id` | `{ns_name_lower: NationalSociety.id}` — for bilateral support and PNS funding rows |
| `ns_home_country_iso3` | `{ns_name_lower: Country.iso3}` — maps PNS name to its home country for template 22 AES lookup |
| `country_id_by_iso3` | `{ISO3: Country.id}` — row key for `country_map` list_library matrices (template 22) |
| `emergency_matrix_plugin_config` | Plugin config from item 960 (filters passed to GO API) |
| `emergency_ops_by_iso` / `_ordered_by_iso` | Lazy GO-API cache per country |
| `staff_matrix_item_id` | `FormItem.id` for the staff matrix on template 22 (auto-created if missing) |
| `warnings` | Accumulated warnings (deduplicated for display) |

---

## 6. Section-by-section mapping

### 6.1 NS Data → Template 24 (scalar items)

- Only rows with a non-empty `indicatorId`; uses `ValueNum`
- `indicatorId` → `FormItem` via `indicator_bank_id`
- Assignment resolved by `(period, ISO3)` → template 24 AES

| indicatorId | Maps to |
|-------------|---------|
| 724 | Volunteers |
| 727 | Staff |
| 1117 | Branches |
| 723 | Local units |

> **Note:** `Area = Total` and `Attribute = Total` for NS Data — these look like aggregates but are the actual values. `is_aggregate_row()` exempts the `NS Data` section from the Total filter.

---

### 6.2 Funding → Templates 24 and 22

The `Source` column determines routing.

#### `Source = Country Data` (or untagged) — → Template 24

Value column: **`Country Value`** (fallback to `ValueNum` for older exports).

| Entity | Target item | Row key |
|--------|-------------|---------|
| `HNS` | 967 / 968 / 974 (year offset 0/1/2) | `HNS` |
| `IFRC Secretariat` | 967 / 968 / 974 | `IFRC Secretariat` |
| `PNS` | 970 / 973 / 975 (year offset 0/1/2) | `NationalSociety.id` of the NS |

Year offset is computed from `Year - period`. Offsets outside 0–2 are skipped.

#### `Source = PNS Data` — → Template 22

Value column: **`PNS Value`**. Only year-offset **0** (current year) is imported (template 22 has a single funding matrix).

Routing chain:

```
NS column (e.g. "Danish Red Cross")
  → NationalSociety.country_id → Country.iso3 = "DNK"
    → template 22 AES for (period, "DNK")
      → item 1303 (Funding Requirements, row_mode=list_library, lookup=country_map)
        → cell key = {host Country.id}_{SP1–EFs}  (e.g. "1_SP1" for Afghanistan)
```

> **Important:** Template 22 AES keys are the **PNS's home country ISO3**, not the host country ISO3. `assignment_by_template[22]` is kept separate from `assignment_by_template[24]` to prevent collisions when the same ISO3 exists in both.

#### `Source = Mix Data` — skipped

All Mix Data rows have `Entity = All-PNS` and `Area = Total` → filtered as aggregates by `is_aggregate_row()`.

---

### 6.3 Reach → Template 24

`Indicator = "People to be reached"`, `ValueNum`.

| Area | Target item | Cell key |
|------|-------------|---------|
| `SP1`–`SP5` | **954** Longer-term programmes | `{Year}_{SP}` e.g. `2026_SP1` |
| `EA1`–`EA3` | **960** Emergency Appeals | `{GO appeal label (CODE)}_Total People to be reached` |
| `EAs` | skipped (aggregate) | |

**Emergency Appeals resolution (EA1/EA2/EA3):**
1. **Primary:** `EA Code` column → look up in GO API for the country using item 960's plugin config (Emergency Appeal type, `end_date_gt: 2025-12-31`, closed ops excluded)
2. **Fallback (no EA Code):** use positional GO slot (EA1 = newest, deterministic order: newest `start_date` first, tie-break by code ascending) — emits a warning
3. **Skip:** blank EA Code + null ValueNum

Row key format: `{operation name} ({code})_Total People to be reached` — must exactly match the `name_with_code` field used by the emergency_operations plugin.

---

### 6.4 Support → Template 24 (bilateral ticks)

- `indicatorId = 3` or `Indicator = "Bilateral Support"`, `ValueNum = 1`
- Target: **item 955** bilateral support matrix (`row_mode=list_library`, `lookup=national_society`)
- Cell key: `{NationalSociety.id}_{SP1–SP5 or EFs}` — value is always `1` (tick)
- NS name resolved via `_resolve_ns_row_id()` (case-insensitive match)

---

### 6.5 Comments → Template 24

- Value from **`Value`** column (not `ValueNum`); falls back to `UPR Value`
- `Area = Total` and `Attribute = Total` — exempted from aggregate filter alongside NS Data
- All comment rows for a country/period are **concatenated** into a single textarea (item **956**), one per line
- Excel indicator codes are humanised:

| Excel indicator | Displayed label |
|-----------------|----------------|
| `Comments_fundingrequirements` | Funding requirements |
| `Comments_keyfigures` | Key figures |
| `Comments_reach` | People to be reached |
| `Comments_support` | Bilateral support |

Unknown `Comments_*` slugs are title-cased automatically.

---

### 6.6 Staff → Template 22

- Section `Staff`, `Entity = PNS`, `ValueNum`
- Target: **item 1367** (`PNS staff contributions` matrix, auto-created if missing)
- Cell key: `{NationalSociety.id}_{column_name}`

| Excel indicator | Matrix column |
|-----------------|--------------|
| # international delegates → HNS | `intl_delegates_hns` |
| # international delegates → IFRC | `intl_delegates_ifrc` |
| # national staff hired through HNS (HNS umbrella) | `national_staff_hns_hns` |
| # national staff hired through HNS (IFRC umbrella) | `national_staff_hns_ifrc` |
| # national staff hired through IFRC (IFRC umbrella) | `national_staff_ifrc_ifrc` |

> **Known issue:** The Staff section currently uses `ISO3` (host country) to resolve the template 22 AES, which is incorrect — template 22 assignments are keyed by the **PNS's home country**. This needs the same NS-name → home-country routing used by PNS Funding. Staff rows will produce 0 records until this is fixed AND 2026 template 22 assignments exist.

---

## 7. Aggregate row filter

`is_aggregate_row()` skips roll-up rows:

- `Area = EAs` always skipped (sum of EA1–EA3)
- `Area in {"Total", "SubTotal"}` skipped **except** in `NS Data` and `Comments` sections (which legitimately use `Area = Total` for their real values)

---

## 8. Cell key formats (summary)

| Item / section | Row key | Column part | Example key |
|----------------|---------|-------------|-------------|
| 954 Longer-term programmes | Calendar year | SP name | `2026_SP1` |
| 955 Bilateral support | `NationalSociety.id` | SP/EFs | `49_SP2` |
| 960 Emergency Appeals | `{name} ({code})` | `Total People to be reached` | `Afghanistan - Earthquake (MDRAF019)_Total People to be reached` |
| 967/968/974 HNS+IFRC funding | Entity name string | SP/EFs | `HNS_SP1`, `IFRC Secretariat_EFs` |
| 970/973/975 PNS funding tpl24 | `NationalSociety.id` | SP/EFs | `140_SP3` |
| 1303 PNS funding tpl22 | `Country.id` (host country) | SP/EFs | `1_SP1` |
| 1367 Staff | `NationalSociety.id` | column name | `49_intl_delegates_hns` |
| 956 Comments | — | — | plain text scalar |

---

## 9. UI wizard

**URL:** `/admin/templates/upr-excel-import/`  
Accessible from the "UPR Excel Sync" button in the Data Sync & Imputation header.

| Step | Panel | What happens |
|------|-------|-------------|
| 1 Upload | `panel-1` | Stores file to `instance/upr_import_uploads/`; saves path in Flask session |
| 2 Review | `panel-2` | Calls `/analyze` → reads sheet, returns row counts, rounds, sections, countries. Shows spinner while loading; result cached so navigating back doesn't re-read. |
| 3 Configure | `panel-3` | Template checkboxes, round filter (blank = all P*), batch size, dry-run toggle. Auto-calls `/preview` on arrival → shows transformed row count, countries, and deduplicated warnings in a scrollable panel. |
| 4 Import | `panel-4` | Async background job via `/run`; polls `/status/<job_id>` every second; shows progress bar. |

### Warning display
Warnings are deduplicated server-side by `summarize_warnings()`:
- Repeated messages are shown once with a count: `National Society not found: 'X' (×12)`
- Header shows total count and unique count: `227 (18 unique)`
- Full list rendered in a scrollable panel (max-height 18 rem)

---

## 10. Shared DB upsert

Both UPR and FDRS importers use `upsert_form_data_rows()` from `import_fdrs_form_data.py`. Each row is a dict with the following string columns:

| Column constant | `form_data` column |
|-----------------|-------------------|
| `COL_ASSIGNMENT` | `assignment_entity_status_id` |
| `COL_ITEM` | `form_item_id` |
| `COL_VALUE` | `value` |
| `COL_DISAGG` | `disagg_data` (JSON) |
| `COL_DATA_NA` | `is_data_not_available` |
| `COL_NA` | `is_not_applicable` |
| `COL_PREFILLED` | `prefilled_value` |
| `COL_IMPUTED` | `imputed_value` |
| `COL_SUBMITTED` | `submitted_at` |

Debug-only fields (`_debug_iso3`, `_debug_year`, `_debug_kpi_code`) are stripped before upsert.

---

## 11. Prerequisites before running P26 import

| Requirement | Status |
|-------------|--------|
| Template 24 (Unified Country Plan) 2026 assignments created | ✅ Done (143 countries) |
| Template 22 (Bilateral Support) 2026 assignments created | ⚠️ Not yet — P26 PNS funding and staff will produce 0 rows until created |
| GO API reachable (for Emergency Appeals resolution) | Runtime dependency |

---

## 12. What is covered (completed)

- [x] Excel reader (`load_upr_data_sheet`) — reads sheet `UPR Data`, skips header rows 1-2, skips blank rows
- [x] Workbook analyzer (`analyze_workbook`) — summary for wizard step 2
- [x] Round → period mapping (`P26` → `2026`)
- [x] Aggregate row filter with NS Data / Comments exemption
- [x] Context builder with per-template assignment maps (no ISO3 collisions)
- [x] NS name index (case-insensitive) → `NationalSociety.id`
- [x] NS name → home country ISO3 index (for PNS funding → template 22)
- [x] ISO3 → `Country.id` index (for `country_map` matrix row keys)
- [x] Template 24: NS Data scalars
- [x] Template 24: Funding — HNS/IFRC and Country-reported PNS → `Country Value` → items 967/968/974/970/973/975
- [x] Template 22: Funding — PNS self-reported → `PNS Value` → item 1303, year-0 only
- [x] Template 24: Reach — SP1–SP5 → item 954 (Longer-term programmes)
- [x] Template 24: Reach — EA1–EA3 → item 960 (Emergency Appeals) via EA Code + GO API fallback
- [x] Template 24: Support — bilateral tick marks → item 955
- [x] Template 24: Comments — human-readable labels, `Value` column, single-newline join → item 956
- [x] Template 22: Staff matrix (auto-created if missing) → item 1367
- [x] Dry-run mode (no DB writes, optional preview Excel output)
- [x] Async background job with progress polling
- [x] 4-step UI wizard with spinners, loading states, disabled nav during async ops
- [x] Warning deduplication with repeat counts
- [x] Shared `upsert_form_data_rows` with FDRS importer

---

## 13. What is pending / known issues

| # | Item | Notes |
|---|------|-------|
| 1 | **Template 22 Staff section AES routing** | Currently uses host ISO3 — must use NS home country (same pattern as PNS Funding). Will silently produce 0 rows until fixed + 2026 tpl22 assignments exist. |
| 2 | **Template 22 Staff matrix row key** | Should be host-country NS id (HNS being supported), not the contributing PNS id. Needs clarification of intended matrix structure. |
| 3 | **Template 22 2026 assignments** | Must be created for each PNS country before P26 PNS Funding or Staff data can be imported. |
| 4 | **Reporting templates (25 + 1 other)** | Not implemented. Require new entries in `UPR_TEMPLATE_PROFILES` and handler blocks in `transform_to_import_rows`. |
| 5 | **NS name fuzzy matching** | Current match is exact case-insensitive. Names that differ by punctuation, accents, or abbreviation (e.g. "The Netherlands Red Cross" vs "Netherlands Red Cross") will warn and be skipped. Consider normalised or phonetic fallback. |
| 6 | **Multi-year PNS Funding in template 22** | Currently only year-offset 0 (current year) is imported. If template 22 is extended with year+1/year+2 funding matrices, the offset restriction should be lifted. |
| 7 | **File locking** | UPR Master.xlsx is locked when open in Excel. Users must copy the file first or close Excel. |
| 8 | **Unit tests** | No automated tests for the transform logic. Key test cases: AFG P26 dry run vs DB, NS name resolution, EA Code vs slot fallback. |

---

## 14. File map

```
Backoffice/
├── scripts/
│   ├── import_upr_excel_data.py       ← main import script (this feature)
│   └── import_fdrs_form_data.py       ← shared upsert helper + FDRS importer
├── app/
│   ├── services/
│   │   └── upr_excel_import_service.py  ← Flask service: upload, analyze, preview, run
│   ├── routes/admin/
│   │   ├── upr_excel_import.py          ← blueprint routes: /admin/templates/upr-excel-import/*
│   │   └── __init__.py                  ← registers upr_excel_import blueprint
│   ├── templates/admin/templates/
│   │   ├── upr_excel_import.html        ← 4-step wizard UI
│   │   └── data_sync_imputation.html    ← links to wizard via "UPR Excel Sync" button
│   └── services/
│       └── emergency_section_binding.py ← GO API slot resolution (used by EA mapping)
├── plugins/emergency_operations/
│   └── routes.py                        ← get_emergency_operations_data()
└── docs/
    └── upr-excel-import.md              ← this document
```

---

## 15. Quick-start commands

```bash
# Analyze workbook only
python scripts/import_upr_excel_data.py --input "UPR Master.xlsx" --analyze-only

# Dry run for P26, templates 24 and 22
python scripts/import_upr_excel_data.py \
  --input "UPR Master.xlsx" \
  --rounds P26 \
  --templates 24,22 \
  --dry-run

# Live import P26
python scripts/import_upr_excel_data.py \
  --input "UPR Master.xlsx" \
  --rounds P26 \
  --templates 24,22

# Targeted dry run for a specific template only
python scripts/import_upr_excel_data.py \
  --input "UPR Master.xlsx" \
  --rounds P26 \
  --templates 24 \
  --dry-run
```

All commands require the Flask app context (`FLASK_CONFIG=development` is set automatically by the script).
