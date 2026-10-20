# FDRS page-level submission

Every FDRS assignment (template 21, all reporting years) must have **Allow save and submit per page** on (`assigned_form.enable_page_submission`).

That flag is what makes each form page its own workflow row in `assignment_page_status`. FDRS already reports workflow separately for the three pages. Until every assignment is in page mode, those KPIs can only be rolled up onto the whole assignment.

This is a **data update**, not a schema migration. The column and `assignment_page_status` table already exist (`add_page_submission`). Do not run `flask db migrate` for this.

## Why

Published FDRS template pages, and the workflow KPI prefix that belongs on each page:

| FDRS prefix | Page name | What the flags mean |
|---|---|---|
| `KPI_NSGS` | NS Governance & Structure | `WasStarted`, `WasSubmitted`, `WasValidated`, `WasPublished`, `ValidationDate`, `PublishDate` |
| `KPI_NSFP` | NS Finance & Partnerships | same suffixes |
| `KPI_NSR` | NS Reach | same suffixes |

Match pages by **name** on the published template version. Page ids differ between databases (local published version 21 uses 76, 77, and 78).

Intended import, once page mode is on everywhere:

- Each prefix is written to `assignment_page_status` for that page, not only folded into `assignment_entity_status`.
- `WasValidated` or `WasPublished` → page `approved`
- `WasSubmitted` → page `submitted`
- `WasStarted` only → page `in_progress`
- No flags for that section → leave the page row unchanged
- `ValidationDate` / `PublishDate` → that page's `status_timestamp` and `submitted_at`
- The whole-assignment status stays the rollup of the three pages (all approved → `approved`, all submitted → `submitted`, any submitted → `submitted`, any started → `in_progress`)

The sync does **not** do this yet. `fdrs_assignment_status_sync.py` still writes only `assignment_entity_status`. The page names live on `FDRS_SECTION_WORKFLOW_SPECS` in `plugins/fdrs/scripts/fdrs_sync_constants.py` so that import can use them.

## What the script changes

`scripts/ops/enable_fdrs_page_submission.py`

- Selects every `assigned_form` with `template_id` = `FDRS_TEMPLATE_ID` (21), including inactive years.
- Skips a year that already has `enable_page_submission` (local 2025 was turned on in the assignment editor). It does not rewrite existing page-status rows.
- For each other year, sets the flag and seeds missing `assignment_page_status` rows the same way the assignment editor does (`apply_page_submission_mode_change`).

Seeded page status is a **copy of the current whole-assignment status**, on every page. It is not the FDRS section status. A partially submitted year can show `submitted` on all three pages until the page-status import above replaces those rows.

## Local

From `Backoffice/`:

```bash
python scripts/ops/enable_fdrs_page_submission.py
python scripts/ops/enable_fdrs_page_submission.py --apply
```

The first command prints a JSON backup (`backup`) and the years it would change (`to_enable`). The second writes and prints `still_off`, which must be `[]`.

## Production

There is no direct database access. The App Service container already has production `DATABASE_URL`. The script is not in the deployed image until this change is released, so upload it with `azure_webapp_run_script.ps1`.

From the repo root, after `az login` on the production subscription:

```powershell
# 1. Preview. Writes nothing. Keep the JSON backup from the log.
.\azure-webapp\azure_webapp_run_script.ps1 -Environment PROD -Script ops/enable_fdrs_page_submission.py `
    *> "$env:TEMP\enable_fdrs_page_submission_prod_dry.log"; "exit=$LASTEXITCODE"

# 2. After the dry run lists the years you expect, apply.
.\azure-webapp\azure_webapp_run_script.ps1 -Environment PROD -Script ops/enable_fdrs_page_submission.py `
    -RemoteArgs "--apply" *> "$env:TEMP\enable_fdrs_page_submission_prod_apply.log"; "exit=$LASTEXITCODE"
```

A run takes about a minute plus the writes (one page-status row per entity per page for each year that was off). Set the shell wait above that. Do not pipe the script output; the `*>` redirect is what keeps the SSH log.

Check the apply log for `"still_off": []`. Re-run without `--apply` if you want to confirm every FDRS year is already enabled.

Take a database snapshot first if you want a rollback point. The write touches every FDRS assignment that is still off and inserts `assignment_page_status` rows. See [Backup & restore](data/backup-and-restore.md).

Staging is the same commands with `-Environment STAGING`.
