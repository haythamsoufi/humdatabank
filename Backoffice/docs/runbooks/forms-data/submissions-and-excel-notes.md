# Forms, Submissions, Excel, and AES Terminology

Operational guide for assignment/form issues, bulk data paths, and terminology that appears in logs, code, and exports.

---

## 1. Terminology: AES (Assignment Entity Status)

The canonical model for tracking a country's progress through a form assignment is `AssignmentEntityStatus` — referred to in code, logs, HTML attributes, and route parameters as **`aes`** or **`aes_id`**.

| Context | Correct name |
|---------|-------------|
| Python model | `AssignmentEntityStatus` |
| Route parameter | `aes_id` |
| HTML data attribute | `data-aes-id` |
| JSON response key | `assignment_entity_status_id` |
| JS variable | `aesId` |

> The legacy name **`acs`** (Assignment Country Status) was fully retired. If you see `acs` in old logs, exports, or comments — it is the same concept. Do not re-introduce `acs` naming in new code.

### AES Status Values

| Status | Meaning |
|--------|---------|
| `draft` | Assignment created but not yet opened to focal points |
| `open` | Focal point can view and edit the form |
| `submitted` | Focal point marked submission complete |
| `approved` | Admin confirmed the data |
| `returned` | Admin sent back for corrections |
| `closed` | Reporting window ended; no further edits |

---

## 2. Debugging Form Behaviour

### Enable verbose form logging

For temporary deep investigation of form save/load/calculation issues:

```bash
# In App Service settings or .env:
VERBOSE_FORM_DEBUG=true
```

This logs every field read, write, and calculation step. **Disable immediately after investigation** — it is noisy and may expose PII in logs.

### Presence (live editing indicator)

If users report conflicts or stale "user is editing" indicators:
- See [Session management](../sessions/session-management.md) §3.
- Presence heartbeats use Redis or in-memory cache — **not** the `user_activity_log` table.
- If presence is stuck (user left without closing tab), it clears automatically after the heartbeat TTL expires (typically 60–120 seconds).

### Form auto-save not working

1. Open browser DevTools → Network tab → reproduce the field edit.
2. Look for the AJAX save request (endpoint: `/forms/assignment/<id>/save` or similar).
3. If the request returns `403` with WAF headers: see [WAF 403 guide](../incidents/waf-403-form-payload-refactor-guide.md).
4. If the request returns `401`: session expired — user must refresh and log back in.
5. If no request is sent at all: JavaScript error — check browser console.
6. Enable `VERBOSE_FORM_DEBUG=true` on the server to see whether saves are reaching the backend.

### CSRF errors on form submit

CSRF tokens expire with the session. If a user left a form open for a long time and then submits:
- Expected behaviour: they get a CSRF error.
- Fix for user: refresh the page (they may lose unsaved data), log back in, and re-submit.
- If CSRF errors are happening immediately after login: check that `SECRET_KEY` is stable across slots and that the load balancer is not mixing sessions across slots.

---

## 3. Excel Import / Export

### Exporting submissions

**Single country:** Admin → Assignment Management → [assignment] → [country row] → Export Excel

**All countries (bulk):** Admin → Assignment Management → [assignment] → Export All → Excel

**Indicator Bank:** Admin → System Admin → Indicator Bank → Export

### What the export contains

- One row per form item per country (or per disaggregation row for demographic breakdowns).
- Calculated fields are included at their computed values (not the formula).
- Empty cells mean the focal point did not save a value for that field.
- Metadata columns: country name, ISO code, assignment period, submission status, last updated.

### Excel import (bulk data upload)

Used to pre-populate or bulk-update submissions from external data sources (e.g. FDRS import).

**CLI:**
```bash
cd Backoffice
python scripts/import_FDRS_data.py
```

**Admin UI import:** Admin → Utilities → Import (if available for the data type)

**When an import fails:**

1. Capture the exact file, worksheet, and first failing row number from the error message.
2. Reproduce on a staging DB snapshot (never experiment with production data directly).
3. Common causes:
   - **Template version mismatch**: the Excel template was built against a different form version than is currently deployed. Check `FormTemplate` item codes match.
   - **Country code not found**: ISO code in the file does not match a country in the DB. Add the country first or correct the code.
   - **Data type mismatch**: a numeric field received text, or vice versa. Clean the source file.
   - **Duplicate rows**: the import script may require unique keys per row.

### Large export timeouts

If a bulk export times out or the server returns a 500:
1. Try exporting one region or one country at a time.
2. Check application logs for memory or timeout errors.
3. If the export is genuinely too large for a single request, consider a CLI-based export script (ask the development team to add one if not available).

---

## 4. Maintenance Scripts (Data)

All scripts run from `Backoffice/` with the virtualenv activated. Always snapshot the DB before running any write script in production.

| Script | Purpose | Typical use |
|--------|---------|-------------|
| `scripts/import_FDRS_data.py` | Bulk import from FDRS data files | Annual data ingestion |
| `scripts/check_db_migration.py` | Sanity-check migration heads | Pre-deploy check |
| `scripts/trigger_automated_trace_review.py` | Export pending AI trace-review packets | Monthly AI quality review |
| `scripts/seed_low_quality_review.py` | Create a test trace review item | QA / pipeline testing |
| `scripts/check_no_console_saved_bypass.py` | CI check: no `__consoleSaved` bypasses in templates | Pre-merge CI |
| `scripts/gate_template_console_calls.py` | Bulk-fix console call patterns in templates | Dev toolchain |

**Before running any write script in production:**
```bash
# 1. Take a DB snapshot
# 2. Read the script's --help output
python scripts/<script>.py --help

# 3. Run on staging first
# 4. Confirm expected output before production
```

---

## 5. Common Submission Issues

| Issue | Likely cause | Fix |
|-------|-------------|-----|
| Focal point cannot find their form | AES status is `draft` or `closed` | Admin → Assignment Management → set AES to `open` |
| Focal point sees form but cannot edit | Incorrect role (View Only) or wrong country assignment | User Management → check role and country |
| Submission shows as "Not started" despite focal point saving | Auto-save may have failed silently | Check `VERBOSE_FORM_DEBUG` logs; confirm no WAF block |
| Exported data shows old values after re-submission | Cache issue or export was run before re-submission completed | Re-export after confirming submission timestamp |
| Disaggregation rows missing from export | Age groups or sex categories not configured | Admin → Settings → Age Groups / Sex Categories |
| Calculated field shows wrong value | Formula references item that was reordered or deactivated | Form Builder → verify formula; rebuild template preview |
| Import fails with "country not found" | ISO code in file does not match DB | Admin → Countries → verify ISO code; correct file or DB |
