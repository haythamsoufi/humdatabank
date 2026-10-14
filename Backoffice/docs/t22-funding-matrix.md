# Template 22 funding matrix (reapply after a database restore)

**Captured:** 13 October 2026, from the local database (template version `updated_at` 2026-10-12 21:19:53 UTC).

Replacing the local database with production **deletes this template configuration**. The Python that reads and imports it stays in git. Apply this document to the restored database before running another UPR planning import, or the import will write column codes the form does not have.

Exact payload: [`t22-funding-matrix.snapshot.json`](t22-funding-matrix.snapshot.json).

| | Local value when captured |
|---|---|
| Template | 22, Planning - International Bilateral Support |
| Published version | 22 |
| Matrix item | 1303, label `Funding Requirements` |

After restore, confirm those ids still point at this template and this matrix. Production may use the same ids if local was cloned from it.

## What to copy back

Onto the published version's **variables**, and onto item 1303's **`config.matrix_config`**. Leave the rest of item 1303's config (layout, privacy, hints) as production has it. The snapshot's `variables` object is the full variable map for the version, not only the funding lookups: replacing the whole map is correct only when production has no extra variables. If it does, merge the 18 `fr_*` keys below and do not drop the others.

## Funding matrix (item 1303)

Rows are the host country (`row_mode` `list_library`, list `country_map`). Column totals are on. Row totals are off. Calculated totals are included in the API.

`include_own_matrix_rows` is on (form builder: Display → Auto Load Entities → "Also list rows from another form filled by the same entity"). Auto-load still lists host countries whose Unified Country Plan mentions this partner. It also lists every country row the same partner saved on template 23 item 1433, in the latest template 23 period (`__latest__`, `Jan-Jun 2026` when captured). Cell values still come from the column lookups, so those extra rows show 0 until the partner types a plan, and saving the form stores them. Submitted, approved and cancelled assignments get no extra rows. `apply_t22_multiyear_funding.py` does not write this block: after a restore, turn it on again in the form builder.

Three column groups. Each has the same eight columns. Codes keep the `[assignment_year]` placeholder; saved cells use the resolved year (`SP1_2026`, `SP1_2027`, `SP1_2028` on a 2026 assignment).

| Offset | Group code | Header (en) | Year header | Table (Funding Requirements) |
|---|---|---|---|---|
| Assignment year | `year_[assignment_year]` | `[assignment_year]` | `#5f97c9` | `#b5d4ef` |
| +1 | `year_[[assignment_year]+1]` | `[[assignment_year]+1]` | `#6aaf58` | `#c3e2b6` |
| +2 | `year_[[assignment_year]+2]` | `[[assignment_year]+2]` | `#c48a28` | `#f0d08a` |

Both colours apply to headers and cells. The year-group colour is the one on the year header; Funding Requirements columns use the lighter subgroup colour. `confirmedfn` has no subgroup, so it keeps the year-group colour.

Subgroup `fun_req` is labelled "Funding Requirements" (ar, es, fr, ru in the snapshot). `confirmedfn` is in the year group and **not** in `fun_req`.

Columns, in order, for each offset. `{year}` means `_[assignment_year]`, `_[[assignment_year]+1]`, or `_[[assignment_year]+2]`.

| Column code | Type | Subgroup | Variable |
|---|---|---|---|
| `SP2{year}` | number, whole | `fun_req` | `fr_sp2` / `fr_sp2_2` / `fr_sp2_3` |
| `SP1{year}` | number, whole | `fun_req` | `fr_sp1` / `fr_sp1_2` / `fr_sp1_3` |
| `SP3{year}` | number, whole | `fun_req` | `fr_sp3` / `fr_sp3_2` / `fr_sp3_3` |
| `SP4{year}` | number, whole | `fun_req` | `fr_sp4` / `fr_sp4_2` / `fr_sp4_3` |
| `SP5{year}` | number, whole | `fun_req` | `fr_sp5` / `fr_sp5_2` / `fr_sp5_3` |
| `EFs{year}` | number, whole | `fun_req` | `fr_efs` / `fr_efs_2` / `fr_efs_3` |
| `fr_tot{year}` | calculated | `fun_req` | none |
| `confirmedfn{year}` | number, whole | none | none |

Each `fr_tot` column sums that year's six SP/EF columns only:

```text
SUM({SP2{year}}, {SP1{year}}, {SP3{year}}, {SP4{year}}, {SP5{year}}, {EFs{year}})
```

Column display names (five languages) are in the snapshot. Do not rename the codes: the importer and the plan visual match `SP1_2026`, `fr_tot_2026`, and `confirmedfn_2026`.

## Variables (published version)

All 18 are lookups on template 24, period `__current__`, entity scope `entities_containing`, return format `auto_load_format`. The column name is the plain area code on the Unified Country Plan matrix (not the T22 column code).

| Variable | Display name | T24 item | T24 column | Plan year |
|---|---|---|---|---|
| `fr_sp1` … `fr_sp5`, `fr_efs` | FR SP1 … FR EFs | **967** | SP1 … SP5, EFs | assignment year |
| `fr_sp1_2` … `fr_sp5_2`, `fr_efs_2` | FR … Second year | **968** | same | +1 |
| `fr_sp1_3` … `fr_sp5_3`, `fr_efs_3` | FR … Third year | **974** | same | +2 |

`fr_efs_2` must read item **968**. `fr_*_3` did not exist before this change; the +2 columns must use them, not the `_2` variables.

## What production will have instead

Until this is reapplied, template 22 has one funding year, column codes such as `SP1` (no year suffix), a single total, and no third-year variables. `fr_efs_2` on that copy reads T24 item 967 (year 1) rather than 968.

## Order after the restore

1. Restore the database.
2. Put this matrix config and these variables back on the published template 22.
3. Then run the UPR planning import. The importer writes `{host_country_id}_SP1_{year}`, `{host_country_id}_fr_tot_{year}`, and `{host_country_id}_confirmedfn_{year}` for the assignment year, +1, and +2.
