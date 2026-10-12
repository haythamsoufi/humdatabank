# Handoff: UPR Master import deleted live PNS reporting matrices

**Status:** Production matrices for Jan-Jun 2026 were restored from DBeaver on 12 Oct 2026. The clear-scope fix is committed (`23d6d940`). The precise-target import and wizard are **uncommitted and not deployed**. Do not run a template 23 UPR Master import on production until both are on the deployed revision.

**Date:** 12 October 2026
**Audience:** Next person touching UPR Excel import, production data, or the admin import wizard
**Related:** [18 Sep bilateral matrix overwrite](../investigations/2026-09-18-bilateral-matrix-overwrite.md) · [UPR Excel import design](../../Backoffice/docs/upr-excel-import.md)

---

## 1. What to do first

1. Do not run `/admin/upr-excel-import` against production with template **23** (Reporting – PNS) until `23d6d940` and the uncommitted target rework below are deployed. The same wipe can happen again on the current production code.
2. Spot-check [assignment 4096](https://databank.ifrc.org/assignment/4096) (Austria, Jan-Jun 2026). The funding matrix (form item 1433) should be populated. Comments were never deleted.
3. Commit the working-tree import rework (file list in §5). Leave `.github/workflows/ios-build.yml` out of that commit. Do not commit `Backoffice/scripts/ops/restore_t23_myr26_funding_matrix_1433.sql` — it embeds production matrix payloads.
4. The earlier annual T23 periods (2021–2025) were also rewritten by the 8 Oct import and have **not** been compared to a dump. See §6.

---

## 2. Two incidents, one form

Both hit template **23**, `assigned_form` **34**, period **Jan-Jun 2026**, form item **1433** (bilateral funding matrix, section “Financial Overview”). Staff item 1434 and comment items 1488/1489 were not the rows that disappeared.

### 18 September 2026 — matrices collapsed, then restored

A UPR Master import (`POST /admin/upr-excel-import/run`, `user_activity_log` 92058, user 1, 10:36 UTC) rewrote partner-NS matrices down to three keys keyed by the reporting country’s own id. Full write-up, AES list, and the 5 Oct restore are in the [18 Sep investigation](../investigations/2026-09-18-bilateral-matrix-overwrite.md).

That restore used `Backoffice/scripts/ops/restore_t23_bilateral_matrix_1433.py` against the 17 Sep dump. 14 matrices updated, 3 inserted (Finland 4099, Netherlands 4108, Testland 4120).

### About 8 October 2026 — matrices deleted

A later UPR Master import deleted item 1433 on the live Jan-Jun 2026 assignments and reset their status to `pending`. Completion was not recomputed at delete time. Opening the form runs `AssignmentCompletionService.refresh_and_persist`, which is why local assignment 4100 showed 100% and then 50% on access, with no save.

Production symptom: [assignment 4096](https://databank.ifrc.org/assignment/4096) showed an empty funding table while comments were still there.

**Cause.** Leaving rounds empty meant “every period” when the importer decided which PNS assignments were non-reported. Any T23 assignment whose PNS was not in the workbook’s “PNS Data” rows for that period had its funding matrix deleted. That included live **MYR26 / Jan-Jun 2026**, which UPR Master must never write or clear. Template 23 only has annual-report assignments (`AR*`); mid-year reporting is template 33.

---

## 3. Production restore (done)

**Script:** `Backoffice/scripts/ops/restore_t23_myr26_funding_matrix_1433.sql` (local; contains production `disagg_data`; do not commit).

**Source dump:** `prod_dump-postgres-202610061721` (6 Oct 2026 17:21). That dump is after the 5 Oct restore and before this wipe. In it, 17 assignments on `assigned_form` 34 had a matrix (14 submitted, 3 in progress), including Austria AES 4096.

**AES restored:** 4089, 4091, 4094, 4096, 4097, 4099, 4100, 4103, 4104, 4105, 4108, 4109, 4110, 4111, 4112, 4114, 4120.

**Guards:**

- Insert item 1433 only when that AES has no 1433 row, so a focal point who re-entered data is not overwritten.
- Restore status / submission metadata only for rows just inserted, and only if the AES is still `pending` with `submitted_at` null.
- Comments and the staff matrix are not written.
- Re-running is safe.

**How it was run.** DBeaver. Ctrl+Enter executes only the statement under the cursor, so the first attempt (SELECTs only) changed nothing and step 3 still showed `with_matrix = 0`. **Alt+X** (Execute script) ran step 2. The operator confirmed that worked on 12 Oct 2026. Expected return: `matrices_restored = 17`, `status_restored = 17`. The step 3 count and a visual check of assignment 4096 were not recorded after that. Completion percentage updates the first time each form is opened.

Other dumps in the repo root (custom format, read with `pg_restore`, not a text search): `prod_dump-postgres-202609171017`, `202609182335`, `202609221725`, `202609301550`, `202610051127`, `202610061721`.

---

## 4. Code that is already committed

Both commits are on the current branch, below `7c3da7c9`. Confirm the deployed production revision contains them before any import. They were not deployed as part of this session.

| Commit | What it does |
|---|---|
| `23d6d940` | `fix(upr): never clear live PNS periods on import; refresh completion after clear` |
| `ea96f39f` | Dashboard Recent Activities no longer drops rows older than 30 days. Unrelated to the matrix delete. The 18 Sep import never wrote `entity_activity_log`, so Austria’s feed was empty because the last real event was 4 Aug. |

`23d6d940` in `Backoffice/plugins/upr/scripts/import_upr_excel_data.py`:

- Consumes the pre-existing closed allowlist `UPR_MASTER_ALLOWED_ROUNDS` (**P23–P26**, **AR21–AR25**, **MYR23–MYR25**) inside the two functions below, so an empty rounds selection falls back to that allowlist instead of “every period”. MYR26, AR26, and P27+ are live and never imported.
- New `pns_clear_periods_for_template`: T22 clears planning periods only; T23 clears annual-report periods only (2021–2025). Jan-Jun 2026 is never cleared.
- New `_refresh_completion_for_aes_ids`: completion is recomputed for the AES ids the clear touched.

That commit stops the live-period delete. It does **not** include `assert_import_scope` — that function, and the hard requirement that rounds be explicit, is part of the uncommitted rework (§5), not this commit. `23d6d940` alone does not yet force the operator to pick one assigned form per (template, round), and does not stop a bad T23 annual-period clear of historical rounds that were actually selected.

---

## 5. Code that is not committed

Working tree as of 12 Oct 2026. This is the “no more confusion” rework. It is not on production.

| Path | Change |
|---|---|
| `Backoffice/plugins/upr/scripts/import_upr_excel_data.py` | New `assert_import_scope` (rounds required, closed allowlist, legal `(template, round)` pairs only — raises before any DB write); row filter is per template; writes confined with `target_aes_ids`; template 22's profile now lists `Funding` too (was `Staff`-only, which forced pairing with 24 just to avoid dropping PNS funding rows) |
| `Backoffice/plugins/upr/scripts/upr_import_targets.py` | **New.** One target = `(template_id, round)` → exactly one assigned form. Plan/verify/run. |
| `Backoffice/plugins/upr/excel/excel_import_service.py` | `plan` / `preview` / `run` take `targets`, not a template list plus an optional round string |
| `Backoffice/plugins/upr/excel/import_routes.py` | `POST /plan`; preview and run reject illegal targets with 400 |
| `Backoffice/plugins/upr/templates/admin/_upr_excel_import_panel.html` | Wizard step 2 is the plan table, not four template checkboxes and a rounds text box |
| `Backoffice/plugins/upr/templates/admin/_upr_excel_import_script.html` | Renders and posts explicit targets |
| `Backoffice/plugins/upr/tests/test_upr_import_targets.py` | **New.** |

`npm run build:css` was run from `Backoffice/` after the wizard markup change.

**Tests on 12 Oct 2026:** `test_upr_import_targets.py`, `test_import_upr_pns_reported.py`, `test_import_upr_cache.py` — 83 passed.

**Wizard (intended layout, not yet checked in a browser):** one row per round; columns **Country** and **PNS**.

| Round | Country column | PNS column |
|---|---|---|
| `P*` | Template 24, Unified Country Plan | Template 22, PNS planning |
| `AR*` | Template 33, country reporting | Template 23, PNS reporting |
| `MYR*` | Template 33 | no cell (template 23 has no mid-year assignments) |

Each cell shows the assigned form id and a status (Ready / Review / Blocked / No data). Blocked and empty cells cannot be selected. Warnings stay behind a Details toggle. A real run that includes a Review target requires the acknowledgement checkbox. The confirm dialog lists each target and its assigned form.

Legal pairs, from `UPR_TEMPLATE_PROFILES`:

```
P*   -> 24 and 22
AR*  -> 33 and 23
MYR* -> 33 only
```

Period names: `P26` → `2026`, `AR25` → `2025`, `MYR25` → `Jan-Jun 2025`.

**Leave out of the import commit:** `.github/workflows/ios-build.yml` (dirty, unrelated).

**Not browser-verified.** After deploy or a local Flask restart, close the Playwright browser and reopen (isolated mode caches the old bundle), log in with the dev “Act as Admin” preset, and walk the wizard through plan → select one country cell and one PNS cell → dry-run preview. Confirm a MYR row has no PNS tick box and that a blocked cell cannot be selected.

`Backoffice/docs/upr-excel-import.md` still describes the pre-target architecture. Update it in the same commit as the rework.

---

## 6. Still open

1. **Confirm the 12 Oct restore on production.** Step 3 of the SQL groups `assigned_form` 34 by status and counts rows that have item 1433. Before the restore, `with_matrix` was 0 for all 33 assignments. After it, 17 of those assignments should have a matrix. Open assignment 4096 and confirm the partner-NS table, not a single row keyed `10_`.
2. **Earlier annual T23 periods.** The 8 Oct import also rewrote T23 annual periods, not only Jan-Jun 2026. Those matrices were not diffed against the 6 Oct dump. If they were deleted or collapsed, they need their own guarded SQL from that dump. Do not reuse the MYR26 script for them; it only inserts the 17 AES ids above, and only for item 1433.
3. **18 Sep leftovers**, still as written in the investigation: whether Finland (4099), Netherlands (4108), and Testland (4120) lost anything besides item 1433; the import change log for `user_activity_log` 92058 (storage category `import_logs`, around 10:36 UTC on 18 Sep 2026). The 6 Oct dump already includes the 5 Oct item-1433 restore, and the 12 Oct SQL put that item back again if it was missing.
4. **Deploy.** Commit §5, ship it with `23d6d940`, then a T23 import is allowed only as explicit targets the plan marks selectable. Historical annual clears still delete non-reported PNS data for the rounds the operator actually selects. That is intended. Live MYR26 must never appear as a selectable T23 target.

---

## 7. Rules for the next import

- Rounds are an explicit list. Empty does not mean all.
- Only the closed allowlist is importable. MYR26, AR26, and P27+ stay out even if the workbook contains them.
- One run writes only the assigned forms for the selected `(template, round)` targets (`target_aes_ids`).
- Template 23 never receives `MYR*` rows and never clears `Jan-Jun 2026`.
- A target with no assigned form, or with more than one, is blocked and must not run.
- Non-reported PNS clearing is limited to periods that template actually imports, and completion is refreshed afterwards.
