# UPR Excel import — review checklist

> **Use this whenever someone asks to review the UPR Excel import.**  
> Review the script, the published form items, **and the template variables**.  
> Design and mapping detail lives in [upr-excel-import.md](upr-excel-import.md).

Last reviewed against the local database: **8 October 2026**.

---

## Why variables are part of the review

The importer writes `form_data`. Template variables (`form_template_version.variables` on the **published** version) decide what the entry form looks up, which matrix rows auto-load, and which saved rows stay marked **manually added**.

A correct write into the current form item still looks wrong when a variable still points at a retired item. That happened on template 22: `fr_sp1`–`fr_sp5` and `fr_efs` read legacy field **970** (the old PNS-only matrix). Lebanon’s Norway amount lives on the current hybrid field **967** (`130_SP3`). After those variables were pointed at **967**, Lebanon auto-loaded on Norway’s funding table (`/assignment/3216`). Switching template 22 from national societies to countries did not break that pair: Norwegian Red Cross and Norway share id **130**, and Lebanese Red Cross and Lebanon share id **101**.

`confirmedfn` is a plain number column. It is not a variable. Auto-load still depends on the SP/EF variables.

---

## Checklist

Run this against the database the import will write to (local, staging, or production). Item ids below are the October 2026 published snapshot. Live import resolves items again in `build_import_context`; treat a resolver warning as a failed check.

1. **Context.** `build_import_context([24, 22, 33, 23])` returns no warnings. Resolved ids match the published matrices in the table below. If they differ, the script snapshot constants are documentation only — the resolved id is the write target.
2. **Columns the script writes** exist on that item:
   - T22 funding: `SP1`–`SP5`, `EFs`, `confirmedfn`, and row totals enabled (cell suffix `Total`, not a named column).
   - T22 staff: `intl_delegates_hns`, `intl_delegates_ifrc`, `national_staff_hns_hns`, `national_staff_hns_ifrc`, `national_staff_ifrc_ifrc`.
   - T24 funding year 0: `SP1`–`SP5`, `EFs`, `EA1`, `EA2`, `EA3`.
   - T24 funding year +1 / +2: `SP1`–`SP5`, `EFs`. EA cells are skipped when those columns are absent.
   - T24 longer-term: `SP1`–`SP5`. Emergency appeals: `Total People to be reached`. Bilateral: `SP1`–`SP5`, `EFs`.
   - T33 funding-by-source column name is `ns_fun`. SP/EF breakdown columns are `Funding (CHF)` and `Expenditure (CHF)`, with the manual row labels in the design doc. Received Support writes `{area} Supported`.
   - T23: `Total Funding`, `Total Expenditure`, `Total Transferred to HNS`. `Funding Requirement` is variable-filled and is not written.
3. **Variables** on each published version (22, 23, 24, 33):
   - `source_form_item_id` exists, is not archived, and belongs to the **published** version of `source_template_id`.
   - The source is the current field, not a retired id (**970 / 973 / 975** legacy PNS funding, **952** old T23 matrix).
   - `matrix_column_name` is a column on that source item, or `_row_total` when row totals are enabled.
   - A published matrix column’s `variable` / `variable_name` actually names this variable.
   - `source_assignment_period` is still the intended round (`__current__`, `__same_year__`, or an explicit year that matches the live cycle).
   - `entity_scope` and `return_format` still match the column. T22 funding auto-load uses `entities_containing` and `auto_load_format`.
4. **Row keys** still match the lookup list:
   - T22 funding (`country_map`): `{host Country.id}_{column}`.
   - T22 staff and T23 funding (`national_society`): `{host NationalSociety.id}_{column}`.
   - T24 hybrid funding PNS rows (`national_society`): `{NationalSociety.id}_{column}`. HNS and IFRC Secretariat use those row labels.
   - When a matrix changes from national societies to countries, confirm the numeric ids in existing cells still match the new lookup. Equal NS and country ids (Norway 130, Lebanon 101) do not prove every other country matches.
5. **Import both sides of a planning round together.** Template 22’s profile section list is Staff only. PNS funding is written from the Funding section when template **24 and 22** are both selected.

---

## 8 October 2026 — local published templates

`build_import_context` returned no warnings. Every resolved id matched the script snapshot.

| Template | Published version | Resolved item | Check |
|----------|-------------------|---------------|--------|
| 22 Planning – International Bilateral Support | version id 22 | **1303** Funding Requirements (`country_map`, auto-load on, row totals on). Columns `SP1`–`SP5`, `EFs`, `confirmedfn`. Stable key `24b9438d-f937-4c99-802a-eccb1ffccc19`. | Import columns match. Extra column `test_total` is on the form and is not written by the import. |
| 22 | same | **1314** Staff contributions (`national_society`). Five staff columns. Stable key `f4fa6b32-3141-4a15-a572-637e7d3f1f94`. | Import columns match. No variables, so staff rows are stored data and are not auto-loaded. |
| 23 Reporting – International Bilateral Support | version id 23 | **1433** untitled matrix, section Financial Overview (`national_society`, auto-load on). | `Total Funding`, `Total Expenditure`, `Total Transferred to HNS` match. |
| 24 Unified Country Plan | version id 24 | **967 / 968 / 974** hybrid funding (`national_society`). | **967** has `EA1`–`EA3`. **968** and **974** do not. EA rows for those offsets are now skipped. |
| 24 | same | **954** longer-term, **960** emergency appeals, **955** bilateral support | Columns match the script. |
| 33 Unified Country Report | version id **37** | **1403** `ns_fun`, **1404** expenditure scalar, **1405** SP/EF breakdown, **1407** Received Support | Columns and manual rows match. |

### Variables on that snapshot

| Variable | Consumer | Source | Result |
|----------|----------|--------|--------|
| `fr_sp1`–`fr_sp5`, `fr_efs` | T22 item 1303 | T24 item **967**, period `__current__`, `entities_containing`, `auto_load_format`, column `SP1`–`EFs` | Current. This is the lookup that auto-loads Lebanon on Norway. |
| `funding_req` | T23 item 1433, column Funding Requirement | T22 item **1303**, `_row_total`, period `__same_year__` | Current. Reads the row total the importer writes as `{Country.id}_Total`. |
| `planned_sp1`–`planned_sp5`, `planned_efs` | T33 item 1407, `{area} Planned` | T24 item **955** (bilateral ticks the importer writes), columns `SP1`–`EFs` | Source item is current. Period is the literal **`2026`**, so a 2025 report still shows 2026 planned ticks. |
| `fdrs_val` | T24 and T33 | Template 21, matched by indicator bank, period literal **`2024`** | Not written by the UPR importer. The year is fixed. |
| `volunteers` | T33 version 37 | Template 21 item **916**, period literal **`2024`** | No published matrix column references it. |

No published matrix column pointed at a variable that is missing from its version. No duplicate indicator-bank ids on these published versions (the last-write-wins bank index was not hiding a second item).

### Code change from this review

Later-year funding matrices have no EA columns. The importer used to write `EA1`–`EA3` onto **968** / **974** anyway. It now skips an EA area when the published matrix schema loads and does not contain that column, and it records one warning. If the schema cannot be read, the cell is still written.
