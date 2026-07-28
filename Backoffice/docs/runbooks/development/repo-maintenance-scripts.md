# Maintenance & CI scripts (`Backoffice/scripts/`)

Loose coupling: run from repo **`Backoffice/`** directory with `.env`/venv activated unless the script documents otherwise.

See **[`scripts/README.md`](../../../scripts/README.md)** for the full folder index.

| Script / topic | Typical use |
|----------------|--------------|
| `ci/check_db_migration.py` | Sanity-check migration heads before upgrades. *(if present)* |
| `ci/check_no_console_saved_bypass.py` | Ensures templates do not bypass client console guards. |
| `ci/gate_template_console_calls.py` | Bulk template console-call fixes (see `tailwind-and-template-safety.md`). |
| `ci/check_translations_current.py` | CI: translations catalog is current and `.po` files compile. |
| `ci/scan_secrets.py` | Repo secret scanning (also in security workflow). |
| `ai/trigger_automated_trace_review.py` | Export pending AI trace-review packets for terminal tooling. |
| `ai/seed_low_quality_review.py` | Deterministic AI review-queue seed for QA. |
| `imports/import_fdrs_form_data.py` | FDRS → form_data sync (CLI and admin data-sync UI). |
| `imports/import_upr_excel_data.py` | UPR Master Excel import (CLI and admin wizard). |
| `codemods/` | Template/JS bulk refactors. See `scripts/codemods/README.md`. |
| `archive/` | Completed one-offs and incident probes — reference only. |

For AI env and health behaviour, combine with [`../observability/logging-and-health.md`](../observability/logging-and-health.md) and [`../../setup/ai-configuration.md`](../../setup/ai-configuration.md).
