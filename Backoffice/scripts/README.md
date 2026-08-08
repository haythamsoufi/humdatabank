# Backoffice scripts

Run from the **`Backoffice/`** directory with venv and `.env` loaded unless a script says otherwise.

## Layout

| Folder | Purpose |
|--------|---------|
| [`ci/`](ci/) | CI guardrails (template safety, secret scanning, script path references) |
| [`i18n/`](i18n/) | Extract, sync, and compile translations |
| [`seeding/`](seeding/) | Dev/test data seeding and reporting-period catalog backfills |
| [`imports/`](imports/) | **Importable modules** — FDRS/UPR Excel pipelines (`import_fdrs_form_data`, `import_upr_excel_data`, …). App code and tests add `scripts/imports` to `sys.path`. |
| [`ai/`](ai/) | AI chat retention and trace-review tooling |
| [`ops/`](ops/) | DB maintenance (sequences, stable keys, integrity checks, load probes) |
| [`dev/`](dev/) | Codegen, audits, smoke tests, manual integration probes |
| [`assets/`](assets/) | Build/vendor assets (e.g. TinyMCE bundle for `npm run vendor:tinymce`) |
| [`codemods/`](codemods/) | Bulk template/JS refactors — see [`codemods/README.md`](codemods/README.md) |
| [`archive/`](archive/) | Completed one-offs and incident probes — reference only |

Shared path helpers: [`_bootstrap.py`](_bootstrap.py).

## Common commands

```bash
# CI guardrails (also run in GitHub Actions)
python scripts/ci/check_no_console_saved_bypass.py
python scripts/ci/check_script_references.py
python scripts/ci/check_script_bootstrap.py

# i18n
python scripts/i18n/extract_update_translations.py --compile
python scripts/ci/check_translations_current.py  # optional sanity check after extract
python scripts/i18n/sync_persistent_translations.py /path/to/persistent/translations

# Data import (CLI)
python scripts/imports/import_fdrs_form_data.py --fdrs-from-data-api --dry-run
python scripts/imports/import_upr_excel_data.py --input "UPR Master.xlsx" --dry-run

# AI trace review export
python scripts/ai/trigger_automated_trace_review.py --status pending --limit 5 --format text
```

See also [`docs/runbooks/development/repo-maintenance-scripts.md`](../docs/runbooks/development/repo-maintenance-scripts.md) and [`Backoffice/README.md`](../README.md).
