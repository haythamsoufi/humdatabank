# Maintenance & CI scripts (`Backoffice/scripts/`)

Loose coupling: run from repo **`Backoffice/`** directory with `.env`/venv activated unless the script documents otherwise.

| Script / topic | Typical use |
|----------------|--------------|
| `check_db_migration.py` | Sanity-check migration heads before upgrades. |
| `check_no_console_saved_bypass.py` | Ensures templates do not bypass client console guards. |
| `gate_template_console_calls.py` | Bulk template console-call fixes (see `tailwind-and-template-safety.md`). |
| `trigger_automated_trace_review.py` | Export pending AI trace-review packets (`ai_trace_reviews` / `ai_reasoning_traces`) for terminal tooling. |
| `seed_low_quality_review.py` | Deterministic AI review-queue seed for QA. |
| Excel / import utilities | Listed in **`Backoffice/README.md`** CLI section |

For AI env and health behaviour, combine with [`../observability/logging-and-health.md`](../observability/logging-and-health.md) and [`../../setup/ai-configuration.md`](../../setup/ai-configuration.md).
