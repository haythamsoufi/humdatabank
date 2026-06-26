# UPR Excel Import — Design, Implementation & Handover Guide

> **Status:** Active / In progress  
> **Last updated:** June 2026  
> **Primary files:** `Backoffice/scripts/import_upr_excel_data.py` · `Backoffice/app/services/upr_excel_import_service.py` · `Backoffice/app/routes/admin/upr_excel_import.py` · `Backoffice/app/templates/admin/templates/upr_excel_import.html`

> **Scope (June 2026):** Planning templates 24 + 22 and Reporting templates 33 + 23 are all implemented. Emergency 1/2/3 sections are intentionally skipped for the first reporting release.

---

## 1. Purpose

Sync planning and reporting data from **UPR Master.xlsx** (sheet `UPR Data`) into form submissions in the Backoffice database. The workbook is the authoritative source for countries' Unified Planning & Reporting data across ~109 k rows and 192 countries.

### Templates in scope

| Template ID | Name | Round prefixes | Sections imported |
|-------------|------|----------------|-------------------|
| **24** | Unified Country Plan | `P*` | NS Data, Funding (country-reported), Reach, Support, Comments |
| **22** | Annual Planning – International Bilateral Support | `P*` | Funding (PNS-reported), Staff |
| **33** | Reporting – Country | `AR*`, `MYR*` | NS Data, Core indicators, Other indicators, Funding, Support |
| **23** | Reporting – PNS | `AR*` | Funding (PNS-reported totals) |

**Emergency 1/2/3 sections** (MDR-scoped indicators) are intentionally skipped for now — see §13.

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
| `Source` | Legacy/metadata: which column `ValueNum` reflects (`Country Data`, `PNS Data`, `Mix Data`). **Not used for import routing** — use `Country Value` / `PNS Value` instead |
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

| Round code | `period_name` | Notes |
|-----------|---------------|-------|
| `P26` | `"2026"` | `2000 + int(round[1:])` |
| `AR25` | `"2025"` | `2000 + int(round[2:])` |
| `MYR26` | `"Jan-Jun 2026"` | `f"Jan-Jun {2000 + int(round[3:])}"` |

The MYR format matches the period_name created for template 33 Mid-Year Review assignments.

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
         "sections": frozenset({"Staff"})},  # PNS Funding handled inside Funding section when 22 ∈ tids
    33: {"name": "Reporting - Country",
         "round_prefixes": ("AR", "MYR"),
         "sections": frozenset({"NS Data", "Funding", "Core indicators", "Other indicators", "Support"})},
    23: {"name": "Reporting - PNS",
         "round_prefixes": ("AR",),
         "sections": frozenset({"Funding"})},
}
```

Adding a new template means adding an entry here and a handler block in `transform_to_import_rows`.

> **Round-type dispatch:** When planning and reporting templates are imported together, each handler checks `rnd_is_planning` (`rnd.startswith("P")`) or `rnd_is_reporting` (`rnd.startswith("AR") or rnd.startswith("MYR")`) to prevent cross-firing on overlapping section names (NS Data, Funding, Support).

---

## 5. Import context (`UprImportContext`)

Built once per import run by `build_import_context()`. Caches all DB lookups so the main loop makes zero extra queries.

| Field | Contents |
|-------|---------|
| `assignment_by_template` | `{template_id: {(period, iso3): aes_id}}` — per-template, no key collisions |
| `assignment_by_period_iso` | Same as `assignment_by_template[24]` — backwards-compat shortcut for non-Funding sections |
| `items_by_bank_id` | `{template_id: {indicator_bank_id: form_item_id}}` — fallback when bank id is unique |
| `items_by_bank_section` | `{template_id: {bank_id: {section_name: form_item_id}}}` — disambiguates duplicate bank ids on reporting-country template |
| `item_ids_by_label` | `{template_id: {label_lower: form_item_id}}` |
| `ns_name_to_id` | `{ns_name_lower: NationalSociety.id}` — for bilateral support and PNS funding rows |
| `ns_home_country_iso3` | `{ns_name_lower: Country.iso3}` — maps PNS name to its home country for template 22 AES lookup |
| `country_id_by_iso3` | `{ISO3: Country.id}` — row key for `country_map` list_library matrices (template 22) |
| `emergency_matrix_plugin_config` | Plugin config from item 960 (filters passed to GO API) |
| `emergency_ops_by_iso` / `_ordered_by_iso` | Lazy GO-API cache per country |
| `staff_matrix_item_id` | Fixed `FormItem.id` **1367** (`PNS staff contributions` matrix on template 22) |
| `iso3_to_hns_id` | `{ISO3: NationalSociety.id}` — host country's primary active NS; row key for T22 Staff and T23 Funding |
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

The `Country Value` and `PNS Value` columns are processed **independently** — a single Excel row can contribute to both templates. The `Source` column is **not** used for routing (it only indicates which column `ValueNum` was derived from in the export).

**Zero / blank values:** Matrix imports skip falsy numeric values (`0`, empty) when writing cells — only non-zero amounts are stored. Scalar NS Data still allows zero KPIs.

#### Country Value → Template 24

| Entity | Target item | Row key |
|--------|-------------|---------|
| `HNS` | 967 / 968 / 974 (year offset 0/1/2) | `HNS` |
| `IFRC Secretariat` | 967 / 968 / 974 | `IFRC Secretariat` |
| `PNS` | 970 / 973 / 975 (year offset 0/1/2) | `NationalSociety.id` of the NS |

Year offset is computed from `Year - period`. Offsets outside 0–2 are skipped. Excel years stored as floats (e.g. `2026.0`) are handled via `int(float(...))`.

> **Period-lookup pitfall:** `_year_offset(period, year_val)` requires `period` from `round_to_period(rnd)` (e.g. `"2026"` for P26). Hard-coding `"2025"` causes funding rows to be silently skipped (wrong offset or `None`). Assignment lookups must use the same dynamic period: `assignment_by_template[tpl][(period, iso3)]`.

#### PNS funding → Template 22 (structured cell format)

Only year-offset **0** (current year) is imported. Rows enter T22 staging when **either** `Country Value` or `PNS Value` is non-zero.

**Two-pass staging:** During the row loop, `(country_val, pns_val)` pairs are collected per `(pns_aes_id, host_country_id, area)`. After all rows, each pair becomes a structured cell on item **1303**.

Routing chain:

```
NS column (e.g. "Netherlands Red Cross")
  → NationalSociety.country_id → Country.iso3 = "NLD"
    → template 22 AES for (period, "NLD")     ← PNS home country, NOT host ISO3
      → item 1303 (Funding Requirements, row_mode=list_library, lookup=country_map)
        → cell key = {host Country.id}_{SP1–EFs}  (e.g. "184_SP2" for Uganda)
```

Each cell is a **structured dict**, not a plain number:

```json
{
  "184_SP2": { "original": 616508, "modified": 439311, "isModified": true  },
  "184_SP1": { "original": 200000, "modified": "",     "isModified": true  },
  "184_EFs": { "original": 0,      "modified": 696998, "isModified": true  },
  "26_EFs":  { "original": 250000, "modified": 250000, "isModified": false },
  "106_EFs": { "original": 328758, "modified": 670961, "isModified": true  }
}
```

| Field | Meaning |
|-------|---------|
| `original` | `Country Value` — what the host country's template 24 reports this PNS contributed (stored as `0` when blank) |
| `modified` | `PNS Value` — what the PNS self-reported; `""` when blank (PNS cleared or did not enter a figure for this area) |
| `isModified` | Per-cell flag — see table below |

**`isModified` rules** (computed per cell after staging):

| Country value | PNS value | PNS reported for this host country? | `isModified` | UI meaning |
|---------------|-----------|-------------------------------------|--------------|------------|
| 250,000 | 250,000 | yes | `false` | PNS confirmed country figure unchanged |
| 616,508 | 439,311 | yes | `true` | PNS changed the amount |
| 200,000 | `""` | yes | `true` | PNS opened the form and cleared the country value |
| 0 | 696,998 | yes | `true` | PNS added a figure the country did not report |
| 200,000 | `""` | no | `false` | Country-only data; PNS has not reported for this country |

**“PNS reported for this host country”** means the PNS has at least one Funding row with a non-zero `PNS Value` for that host country in the Excel (any area). Once true, all staged areas for that `(PNS assignment, host country)` pair participate in per-cell comparison: `isModified = (pns_value_as_number ≠ country_value_as_number)` where blank/`None` counts as `0` for comparison only (stored `modified` remains `""`).

**Worked example — Netherlands Red Cross × Uganda (P26):**

| Area | Country Value (→ tpl 24 Uganda) | PNS Value (→ tpl 22 Netherlands) | T22 cell |
|------|--------------------------------|-------------------------------------|----------|
| EFs | — | 696,998 | `{ original: 0, modified: 696998, isModified: true }` |
| SP1 | 200,000 | — | `{ original: 200000, modified: "", isModified: true }` *(PNS reported elsewhere for Uganda)* |
| SP2 | 616,508 | 439,311 | `{ original: 616508, modified: 439311, isModified: true }` |
| SP3 | 355,652 | — | `{ original: 355652, modified: "", isModified: true }` |
| SP4 | 206,160 | — | `{ original: 206160, modified: "", isModified: true }` |

Country-reported figures land on the **Uganda** template 24 assignment; PNS self-report lands on the **Netherlands** template 22 assignment (item 1303), keyed by Uganda's `Country.id` as the matrix row.

> **Important:** Template 22 AES keys are the **PNS's home country ISO3**, not the host country ISO3. `assignment_by_template[22]` is kept separate from `assignment_by_template[24]` to prevent collisions when the same ISO3 exists in both.

#### Form UI display (`matrix-handler.js`)

Variable funding columns read `{ original, modified, isModified }` from `disagg_data`. Display value uses `modified != null ? modified : original` so that `modified: ""` (cleared) shows as **blank**, not the original amount. Green/orange modification styling follows the stored `isModified` flag.

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

- Section `Staff`, `Entity = PNS`, non-zero `ValueNum` only
- Target: **item 1367** (`PNS staff contributions` matrix — fixed ID)
- AES resolved by **PNS home country ISO3** (same path as PNS Funding, via `ns_name → ns_home_country_iso3`)
- Row key: **host country's `NationalSociety.id`** (`iso3_to_hns_id[host_ISO3]`) — the HNS receiving staff
- Column key: indicator string mapped via `STAFF_INDICATOR_COLUMNS`

| Excel indicator | Matrix column |
|-----------------|--------------|
| # international delegates → HNS | `intl_delegates_hns` |
| # international delegates → IFRC | `intl_delegates_ifrc` |
| # national staff hired through HNS (HNS umbrella) | `national_staff_hns_hns` |
| # national staff hired through HNS (IFRC umbrella) | `national_staff_hns_ifrc` |
| # national staff hired through IFRC (IFRC umbrella) | `national_staff_ifrc_ifrc` |

> **Note:** T22 form only has one Funding Requirements matrix (item 1303) with no year+1/+2 equivalents. Multi-year PNS Funding for T22 requires additional form items before the import restriction can be removed.

---

### 6.7 NS Data → Template 33 (reporting, scalar)

- Same `indicatorId` lookup as T24: bank IDs 723 / 724 / 727 / 1117
- `Data_EO*` and `Data_MDR*` indicators (no `indicatorId`) are **skipped**
- AES resolved by `(period, ISO3)` → template 33 assignment map

---

### 6.8 Core indicators + Other indicators → Template 33

- Sections `Core indicators` and `Other indicators`, `Entity = HNS`
- `indicatorId` + Excel `Area` → `FormItem` (same bank id can appear on multiple section-scoped items)
- Excel `Area` → form section:

| Excel `Area` | Form section |
|--------------|--------------|
| `Cross-cutting` | Cross Cutting |
| `SP1` | Resilience - Climate and environment |
| `SP2` | Response - Disasters and crises |
| `SP3` | Resilience - Health and wellbeing |
| `SP4` | Resilience - Migration and displacement |
| `SP5` | Respect - Values, power and inclusion |
| `EF1` | Strategic and operational coordination |
| `EF2` | National Society development |
| `EF3` | Humanitarian diplomacy and communication |
| `EF4` | Accountability and agility |

> **Example:** bank id **619** exists on two section-scoped items (Cross Cutting and Response - Disasters and crises). The Cross-cutting Excel row must land on the Cross Cutting item; the SP2 row on the SP2 section item. Resolved via `items_by_bank_section` + Excel `Area`.

- If `Applicable/Data not available` contains "data not available" → writes `is_data_not_available = True` (no value)
- Otherwise uses `ValueNum` as a scalar

---

### 6.9 Funding → Templates 33 and 23 (reporting)

**Template 33 — HNS Expenditure (scalar, item 1404):**
- `Entity = HNS`, `Attribute = Total`, `Indicator = Expenditure` (`indicatorId = 734`), `ValueNum`
- Resolved via `items_by_bank_id[33][734]`

**Template 33 — Optional SP/EF breakdown (matrix, item 1405):**
- Rows collected where `Section = Funding`, `Entity = HNS`, `Attribute = "SP Breakdown"`
- `Area` → matrix row (SP1–SP5, EFs mapped to the manual row labels on item 1405)
- `Indicator = Funding` (`indicatorId = 733`) → column `Funding (CHF)`
- `Indicator = Expenditure` (`indicatorId = 734`) → column `Expenditure (CHF)`
- Cell key: `{row_label}_{column}` e.g. `Resilience - Climate and environment_Funding (CHF)`

| Excel `Area` | Matrix row |
|--------------|------------|
| `SP1` | Resilience - Climate and environment |
| `SP2` | Response - Disasters and crises |
| `SP3` | Resilience - Health and wellbeing |
| `SP4` | Resilience - Migration and displacement |
| `SP5` | Respect - Values, power and inclusion |
| `EFs` | Enabling functions |

**Template 33 — Total Funding by source (matrix, item 1403):**
- Rows collected where `Attribute = "Funding Source"` AND `indicatorId = 733`
- `Entity = IFRC Secretariat` → row `IFRC Secretariat`
- `Entity = PNS` (excluding NS name `Country`) → accumulated into row `PNSs`
- `Entity = Other sources` → row `HNS other sources`
- Single column `NS 2025 Total Funding`; cell key = `{row_name}_NS 2025 Total Funding`

**Template 23 — PNS-reported Funding (matrix, item 952):**
- `Entity = PNS`, NS name → home country ISO3 → template 23 AES
- Row key: `iso3_to_hns_id[host_ISO3]` (the host country's primary NS)
- Columns: `Total Funding` (iid 733), `Total Expenditure` (iid 734), `Total Transferred to HNS` (iid 5, from `00005`)
- `Funding Requirement` (iid 2, `00002`) is pre-filled from planning (variable/readonly) — skipped

---

### 6.10 Support → Template 33 (Received Support)

- Section `Support`, `Entity = PNS`, `ValueNum = 1`, non-aggregate Area
- Target: **item 1407** (`Received Support`, list_library national_society)
- Row key: `NationalSociety.id` of the PNS (from `NS` column)
- Column key: `{area} Supported` — e.g. `SP1 Supported`, `EFs Supported`
- Paired `{area} Planned` columns are pre-filled from planning (variable/readonly) — not written by import

---

## 7. Aggregate row filter

`is_aggregate_row()` skips roll-up rows:

- `Area = EAs` always skipped (sum of EA1–EA3)
- `Area in {"Total", "SubTotal"}` skipped **except** in `NS Data` and `Comments` sections (which legitimately use `Area = Total` for their real values)

---

## 8. Cell key formats (summary)

### Planning

| Item / section | Row key | Column part | Example key |
|----------------|---------|-------------|-------------|
| 954 Longer-term programmes | Calendar year | SP name | `2026_SP1` |
| 955 Bilateral support | `NationalSociety.id` | SP/EFs | `49_SP2` |
| 960 Emergency Appeals | `{name} ({code})` | `Total People to be reached` | `Afghanistan - Earthquake (MDRAF019)_Total People to be reached` |
| 967/968/974 HNS+IFRC funding | Entity name string | SP/EFs | `HNS_SP1`, `IFRC Secretariat_EFs` |
| 970/973/975 PNS funding tpl24 | `NationalSociety.id` | SP/EFs | `140_SP3` |
| 1303 PNS funding tpl22 | `Country.id` (host country) | SP/EFs | `184_SP2` — value is `{"original":616508,"modified":439311,"isModified":true}` |
| 1367 Staff | host `NationalSociety.id` (HNS) | column name | `49_intl_delegates_hns` |
| 956 Comments | — | — | plain text scalar |

### Reporting

| Item / section | Row key | Column part | Example key |
|----------------|---------|-------------|-------------|
| 1404 Reporting Expenditure | — | — | plain scalar (`Attribute = Total`) |
| 1405 Reporting SP/EF breakdown | manual row label | `Funding (CHF)` / `Expenditure (CHF)` | `Resilience - Climate and environment_Funding (CHF)` |
| 1403 Reporting Total Funding | row name string | `NS 2025 Total Funding` | `PNSs_NS 2025 Total Funding` |
| 1407 Reporting Received Support | `NationalSociety.id` (PNS) | `{area} Supported` | `49_SP1 Supported` |
| 952 T23 PNS Funding | host `NationalSociety.id` (HNS) | column name | `49_Total Funding` |

---

## 9. UI wizard

**URL:** `/admin/templates/upr-excel-import/`  
Accessible from the "UPR Excel Sync" button in the Data Sync & Imputation header.

| Step | Panel | What happens |
|------|-------|-------------|
| 1 Upload | `panel-1` | Drag/drop or click to select file. The dropzone validates the file type/size client-side, then POSTs to `/upload` (server-side MIME + extension check), then immediately POSTs to `/analyze` (reads the "UPR Data" sheet). The workbook summary (rows, countries, rounds, sections) appears in the dropzone status panel on success, or an error message on failure. The **Next** button is only enabled after analyze succeeds. |
| 2 Configure | `panel-2` | Template checkboxes, round filter (blank = all P*), batch size, dry-run toggle. **Preview import** (optional) calls `/preview` on demand and shows transformed row count, countries, and deduplicated warnings. **Run import** is available immediately after configuring settings; preview is not required. |
| 3 Import | `panel-3` | Async background job via `/run`; polls `/status/<job_id>` every second; shows progress bar. |

### Warning display
Warnings are deduplicated server-side by `summarize_warnings()`:
- Messages that differ only by country and/or round are **grouped** — e.g. `No reporting-country form item for area 'SP1' (×96, 92 countries, 8 indicators, AR25)`
- Exact duplicates (e.g. repeated NS name typos) show once with a count: `National Society not found: 'X' (×12)`
- Header shows total count and unique count: `227 (18 unique)`
- Full list rendered in a scrollable panel (max-height 18 rem)

### Template version routing (T33)

When a template has a **deployed v2** (previous version archived), the import resolves form items per row:

| Round / period | Template version |
|----------------|------------------|
| `AR25`, `MYR25`, … (calendar year &lt; 2026) | Legacy (archived) version |
| `MYR26`, `AR26`, … (calendar year ≥ 2026) | Current published version |

Special matrix items (NS Total Funding, Expenditure, SP/EF breakdown, Received Support) are resolved by **label** within the chosen version, not hardcoded item ids. Indicator bank-id lookups use the same version index.

Other templates (24, 22, 23) load legacy + current indexes when both exist; only T33 applies the 2026 cutoff today. Planning templates typically have a single published version.

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

### Re-running the sync

Upsert key: `(assignment_entity_status_id, form_item_id)`.

| Situation | Behaviour |
|-----------|-----------|
| Excel has data for an item | Existing `form_data` row is **updated** (scalar `value` or full `disagg_data` JSON replaced) |
| Excel has no row for an item | Existing DB row is **left unchanged** |
| Matrix item (e.g. 1303) | Entire `disagg_data` object is replaced — cells not in the new payload disappear from stored JSON |
| Manual edits on items the script never writes | Untouched |

Re-importing after a logic fix (e.g. period lookup, `isModified` rules) overwrites prior incorrect matrix JSON for items the transform emits again.

---

## 11. Prerequisites before running an import

### Planning (P rounds)

| Requirement | Status |
|-------------|--------|
| Template 24 (Unified Country Plan) 2026 assignments created | ✅ Done (143 countries) |
| Template 22 (Bilateral Support) 2026 assignments created | Required for PNS funding (item 1303) and staff — one assignment per PNS home country |
| GO API reachable (for Emergency Appeals resolution) | Runtime dependency |

### Reporting (AR rounds — templates 33 + 23)

| Requirement | Status |
|-------------|--------|
| Template 33 (Reporting – Country) assignments created with `period_name = '{year}'` | Required per AR round year |
| Template 23 (Reporting – PNS) assignments created with `period_name = '{year}'` | Required — one per PNS home country |

### Reporting (MYR rounds — template 33 only)

| Requirement | Status |
|-------------|--------|
| Template 33 (Reporting – Country) assignments created with `period_name = 'Jan-Jun {year}'` | Required — e.g. `'Jan-Jun 2026'` (✅ done for MYR26) |

---

## 12. What is covered (completed)

### Core infrastructure
- [x] Excel reader (`load_upr_data_sheet`) — reads sheet `UPR Data`, skips header rows 1-2, skips blank rows
- [x] Workbook analyzer (`analyze_workbook`) — summary with planning / AR / MYR round lists
- [x] Round → period mapping: `P26` → `"2026"`, `AR25` → `"2025"`, `MYR26` → `"Jan-Jun 2026"`
- [x] Aggregate row filter with NS Data / Comments exemption
- [x] Round-type dispatch (`rnd_is_planning` / `rnd_is_reporting`) prevents cross-fire when mixed templates run together
- [x] Context builder with per-template assignment maps (no ISO3 collisions)
- [x] NS name index (case-insensitive) → `NationalSociety.id`
- [x] NS name → home country ISO3 index
- [x] ISO3 → `Country.id` index (for `country_map` list_library matrices)
- [x] ISO3 → `NationalSociety.id` index for host country's primary NS (T22 Staff + T23 Funding row keys)
- [x] Dry-run mode (no DB writes, optional preview Excel output)
- [x] Async background job with progress polling
- [x] 3-step UI wizard: Upload+Analyze inline (step 1), Configure (step 2), Import (step 3)
- [x] Warning deduplication with repeat counts
- [x] Shared `upsert_form_data_rows` with FDRS importer

### Planning (rounds P*)
- [x] Template 24: NS Data scalars
- [x] Template 24: Funding — HNS/IFRC and Country-reported PNS → `Country Value` → items 967/968/974/970/973/975
- [x] Template 22: Funding — `{original, modified, isModified}` structured cells on item 1303; per-cell `isModified`; zero-skip
- [x] Template 24: Reach — SP1–SP5 → item 954; EA1–EA3 → item 960 via EA Code + GO API fallback
- [x] Template 24: Support — bilateral tick marks → item 955
- [x] Template 24: Comments — human-readable labels, `Value` column, single-newline join → item 956
- [x] Template 22: Staff — AES via PNS home country ISO3; row key = host `NationalSociety.id` → item 1367

### Reporting (rounds AR*, MYR*)
- [x] Template 33: NS Data scalars (bank IDs 723/724/727/1117); `Data_EO*`/`Data_MDR*` skipped
- [x] Template 33: Core indicators + Other indicators → scalar by `indicator_bank_id`; `is_data_not_available` flag written when Excel marks row as unavailable
- [x] Template 33: Funding — HNS Expenditure total → item 1404 (scalar, `Attribute = Total`); SP/EF breakdown → item 1405 (matrix, `Attribute = SP Breakdown`); IFRC/PNS/Other by Funding Source rows → item 1403 (manual matrix)
- [x] Template 33: Support — bilateral ticks → item 1407 `{area} Supported` columns
- [x] Template 23: Funding — PNS totals (Funding/Expenditure/Transferred) → item 952; row = host `NationalSociety.id`; AES via PNS home country
- [x] Form UI: variable matrix cells honour `modified: ""` as cleared (not fallback to `original`)

---

## 13. What is pending / known issues

| # | Item | Notes |
|---|------|-------|
| 1 | **Emergency 1/2/3 sections (reporting)** | Skipped. These sections carry indicators scoped to specific MDR appeal codes (`SectionB`). Implementing them requires understanding the storage format of `plugin_emergency_operations` item 1302 and mapping MDR codes to matrix row keys. |
| 2 | **Multi-year PNS Funding in template 22** | T22 form (item 1303) has only one Funding Requirements matrix with SP1–SP5/EFs columns — no year+1/+2 equivalents exist. Adding year+1/+2 support requires new form items before the import can write them. |
| 3 | **Template 22-only import skips PNS funding** | `UPR_TEMPLATE_PROFILES[22]` lists only `Staff` for row filtering. PNS Funding is written from the `Funding` section when template 22 is also included — run with **both 24 and 22** (default in the wizard). |
| 4 | **NS name exact matching** | Match is case-insensitive but exact. Names differing by punctuation or abbreviation (e.g. "The Netherlands Red Cross" vs "Netherlands Red Cross") produce a warning and are skipped. Fuzzy matching is intentionally not implemented. |
| 5 | **File locking** | UPR Master.xlsx is locked when open in Excel. Users must copy the file first or close Excel. |
| 6 | **Unit tests** | No automated tests for the transform logic. Key test cases: AFG P26 dry run vs DB, NS name resolution, EA Code vs slot fallback, Netherlands×Uganda T22 `{original, modified, isModified}`, AR25/MYR26 period resolution. |

---

## 14. File map

```
Backoffice/
├── scripts/
│   ├── import_upr_excel_data.py       ← main import script (this feature)
│   └── import_fdrs_form_data.py       ← shared upsert helper + FDRS importer
├── app/
│   ├── static/js/forms/modules/
│   │   └── matrix-handler.js            ← variable matrix {original, modified, isModified} display
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
# Analyze workbook only (shows all rounds, sections, row counts)
python scripts/import_upr_excel_data.py --input "UPR Master.xlsx" --analyze-only

# ── Planning ──────────────────────────────────────────────────────────────────

# Dry run for P26 (templates 24 + 22)
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

# ── Reporting — Annual Report (AR) ────────────────────────────────────────────

# Dry run for AR25 (country + PNS reporting)
python scripts/import_upr_excel_data.py \
  --input "UPR Master.xlsx" \
  --rounds AR25 \
  --templates 33,23 \
  --dry-run

# Live import AR25
python scripts/import_upr_excel_data.py \
  --input "UPR Master.xlsx" \
  --rounds AR25 \
  --templates 33,23

# ── Reporting — Mid-Year Review (MYR) ─────────────────────────────────────────
# T23 has no MYR assignments — use template 33 only.

# Dry run for MYR26
python scripts/import_upr_excel_data.py \
  --input "UPR Master.xlsx" \
  --rounds MYR26 \
  --templates 33 \
  --dry-run

# Live import MYR26
python scripts/import_upr_excel_data.py \
  --input "UPR Master.xlsx" \
  --rounds MYR26 \
  --templates 33
```

All commands require the Flask app context (`FLASK_CONFIG=development` is set automatically by the script).
