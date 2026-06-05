# FDRS sync coverage and progress (template 21)

Track what the FDRS import pipeline (`Backoffice/scripts/import_fdrs_form_data.py`) fills from [data-api.ifrc.org](https://data-api.ifrc.org), and what remains manual or blocked.

**Last updated:** 2026-06-05

## Summary

| Category | Template items | Sync status |
|---|---:|---|
| Indicators (via indicator bank `fdrs_kpi_code`) | 28 | **Synced** |
| Questions (direct KPI map) | 5 | **Synced** |
| Income Sources matrix | 1 (943) | **Synced** (matrix `disagg_data`) |
| Document fields | 4 | **Metadata synced**; file download **blocked** (IFRC URL fix pending) |
| Network Support matrices | 2 (919, 929) | **Synced** (CSV DonCode + amount KPIs → matrix `disagg_data`) |
| Assignment workflow | per `(country, year)` | **Synced** (section workflow KPIs → `assignment_entity_status`) |
| **Total published items** | **40** | **40 covered** |

## Done

### Indicators and disaggregation

- All published template indicators with `indicator_bank.fdrs_kpi_code` (including **935 volunteer deaths** after bank KPI fix).
- Sex/age/indirect via `disagg_data` on reach and governance indicators.
- Disability questions (`_ddd` / `_wgq` logical KPIs) → `disagg_data.values.disability` on matching indicators (when form item has **Allow disability questions** enabled, entry form shows the same fields).
- `data_not_available` / `not_applicable` from `_IsDataNotAvailable` / `_isDataNotCollected` KPI variants.

### Questions (direct KPI → item map)

| item_id | Label | FDRS KPI |
|---:|---|---|
| 924 | Sex of president | `KPI_pr_sex` |
| 934 | Sex of Secretary General | `KPI_sg_sex` |
| 918 | Reporting currency | `KPI_CUR_Code` |
| 928 | Financial reporting start date | `KPI_StartDate` |
| 937 | Financial reporting end date | `KPI_EndDate` |

Constants: `Backoffice/scripts/fdrs_sync_constants.py` → `FDRS_QUESTION_KPI_TO_ITEM`.

### Income Sources matrix (item 943)

- FDRS income-source KPIs (`h_gov_CHF`, `corp_CHF`, …) aggregated per `(ISO3, year)` into matrix cells `{row_label}_Funding`.
- Builder: `build_income_sources_matrix_rows()` in `import_fdrs_form_data.py`.
- Row map: `FDRS_INCOME_KPI_TO_MATRIX_ROW` in `fdrs_sync_constants.py` (aligned with `fdrs_v1_catalog.INCOME_SOURCE_KPI_CODES`).

### Network Support matrices (items 919, 929)

- FDRS stores bilateral NS support as parallel CSV fields per slot (1–10):
  - **919** (support given): `supported{N}` (DonCodes) + `supported{N}_amount`
  - **929** (support received): `received_support{N}` + `received_support{N}_amount`
- Builder: `build_network_support_matrix_rows()` in `import_fdrs_form_data.py`.
- DonCode → matrix row label via `NationalSociety.name` (country iso3) with fallback to entities/ns `NSO_DON_name`.
- Matrix cell keys: `{NS Name}_Funding provided` / `{NS Name}_Funding Received`.

### Assignment workflow (`assignment_entity_status`)

- FDRS exposes **per-section** workflow KPIs (Governance `KPI_NSGS_*`, Finance `KPI_NSFP_*`, Reach `KPI_NSR_*`):
  - `WasStarted`, `WasSubmitted`, `WasValidated`, `WasPublished`
  - `ValidationDate`, `PublishDate` (ISO datetimes on raw fdrsdata rows)
- Module: `Backoffice/scripts/fdrs_assignment_status_sync.py` (runs after form_data upsert).
- Mapping to databank status:
  - all 3 sections validated/published → `approved`
  - all 3 submitted → `submitted`
  - any section submitted/validated → `submitted` (partial)
  - any section started only → `in_progress`
- Sets `status_timestamp` / `submitted_at` from FDRS dates when available.
- Does **not** set `submitted_by_user_id` / `approved_by_user_id` (FDRS has no user identity).
- Skips downgrades (e.g. won't move `approved` → `submitted`) and preserves `sent_for_review` / `requires_revision` unless FDRS is fully validated (`approved`).
- CLI opt-out: `--no-sync-assignment-status`.

### Documents (metadata only)

- API: `GET /api/documents?apiKey=…&showunpublished=true&force=true[&year=YYYY]`
- Module: `Backoffice/scripts/fdrs_documents_sync.py`
- Maps FDRS `document_type` → form items 923, 933, 1309, 1310.
- Creates/updates `SubmittedDocument` with `source_url`, `file_pending=true`, `storage_path=NULL`.
- Idempotency: `fdrs_import_key` (unique).
- **File URLs return HTTP 403** from `https://data-api.ifrc.org/documents/…` — awaiting IFRC fix; then re-run sync to download bytes into storage.

Migration: `add_fdrs_submitted_document_metadata.py` (`source_url`, `thumbnail_source_url`, `fdrs_import_key`, `file_pending`, nullable `storage_path`).

## Blocked / not implemented

### Document file bytes

- **Blocker:** IFRC static document URLs not served (403).
- **Action:** IFRC fixes URL serving or documents authenticated download endpoint.
- **Then:** Re-run FDRS sync; extend `fdrs_documents_sync.py` to download → `save_submission_document` and clear `file_pending`.

## How to run

Admin UI: **Special template → FDRS Data Sync** (same job as KPI sync; documents run after form_data upsert).

CLI:

```bash
cd Backoffice
python scripts/import_fdrs_form_data.py --fdrs-from-data-api --fdrs-years 2024
```

Optional env:

- `FDRS_DATA_API_KEY` — required for data-api.ifrc.org
- `FDRS_SYNC_USER_ID` — user id for imported document rows (defaults to first active user)

Dry-run still counts document rows when `dry_run=true`.

## Tests

- `Backoffice/tests/unit/test_fdrs_sync_helpers.py` — income matrix, network support matrix, assignment status, document plan

## Change log

| Date | Change |
|---|---|
| 2026-06-05 | Disability `_ddd` / `_wgq` KPIs merged into `disagg_data.values.disability` on indicator sync |
| 2026-06-05 | Assignment workflow sync from FDRS section WasSubmitted/WasValidated KPIs |
| 2026-06-05 | Network Support matrices 919/929 synced from supported*/received_support* KPI CSV pairs |
| 2026-06-05 | Income matrix 943, finance questions 918/928/937, document metadata sync, progress doc created |
| 2026-06-05 | User fixed item 935 `fdrs_kpi_code` in indicator bank |
