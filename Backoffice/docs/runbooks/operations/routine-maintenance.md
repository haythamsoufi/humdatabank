# Routine Maintenance

Recurring operational tasks for keeping the Humanitarian Databank Backoffice healthy. Run these on the schedules below. All CLI commands run from the `Backoffice/` directory with the virtual environment activated.

---

## Weekly Checks

### 1. Session Cleanup

Remove expired and orphaned sessions to keep the session table lean:

```bash
cd Backoffice
python -m flask cleanup-sessions
```

Expected output: a count of removed sessions. If you see 0 sessions removed repeatedly, cleanup may already be running automatically — check your scheduled tasks/cron.

### 2. Review Active Sessions (Spot-Check)

```bash
python -m flask show-all-sessions
```

Look for:
- Unexpectedly long-running sessions (users who should have logged out weeks ago).
- Sessions for users who have been deactivated (should not exist — if found, rotate `SECRET_KEY` after investigation).
- Unusual session counts from a single IP (potential scripted access).

### 3. Application Health Check

Confirm the app is running and AI subsystems are healthy:

```bash
# From a browser or curl:
GET https://<your-app-url>/api/ai/v2/health
```

Expected JSON: `{ "status": "ok", "agent_available": true, "providers": { ... } }`.  
If `status` is `degraded` or a provider shows as unavailable, see [Logging & health](../observability/logging-and-health.md) and [AI configuration](../../setup/ai-configuration.md).

### 4. Log Review

Stream and review recent application logs:

```bash
az webapp log tail --name <webapp-name> --resource-group <rg-name>
```

Look for:
- `ERROR` or `CRITICAL` level entries not seen before.
- Repeated 4xx/5xx on specific endpoints.
- RBAC audit warnings on startup (`WARNING ... unguarded admin route`).
- Database connection errors or slow query warnings.

---

## Monthly Tasks

### 5. Database Migration Head Check

Before any month-end maintenance window or after any code deployment:

```bash
python -m flask db heads
```

Must return **exactly one head**. If you see two or more, escalate to the development team immediately — do not run `db upgrade` with multiple heads.

### 6. AI Trace Review Queue

If the AI chat system is enabled, review pending low-quality trace reviews:

```bash
cd Backoffice
python scripts/trigger_automated_trace_review.py --status pending --limit 20 --format text
```

This exports trace packets flagged for review. Review them with your AI quality process and mark as resolved.

To seed a test item for verifying the review pipeline:
```bash
python scripts/seed_low_quality_review.py
```

### 7. Indicator Bank Embedding Sync

After any bulk edits to the Indicator Bank (new indicators, name/definition changes):

```bash
python -m flask sync-indicator-embeddings
```

This regenerates vector embeddings used by AI search. Costs a small amount in OpenAI embedding API credits. Skip if you have not changed the Indicator Bank this month.

### 8. Translation Sync Check

If LibreTranslate is used and new content was added during the month:

1. Admin → Translations → review untranslated items (shown with a warning or empty cell).
2. Run auto-translate for the affected language(s) if the service is available.
3. Spot-check a sample of auto-translated labels for accuracy.

### 9. User Account Audit

Review active accounts to catch stale access:

1. Admin → User Management → export or scroll all users.
2. Cross-reference with current staff list.
3. Deactivate accounts for staff who have left or changed roles.
4. Confirm self-service **Access Requests** have been processed (no stale pending rows).

---

## Quarterly Tasks

### 10. Backup Verification

Confirm that database backups are completing and restorable:

1. Verify scheduled `pg_dump` jobs completed successfully (check backup storage logs).
2. Restore the latest backup to a staging/test environment.
3. **Azure PostgreSQL Flexible Server (private networking):** If your DR path restores into a **new** server instance, assume **private endpoints must be recreated by infrastructure** before the app can connect — coordinate with infra before declaring the drill successful (see [Backup & restore](../data/backup-and-restore.md) §2).
4. Run smoke test on restored environment:
   ```bash
   python -m flask db current          # confirm migration revision
   GET /api/ai/v2/health               # confirm AI subsystem
   ```
5. Document the restore test result and date.

See [Backup & restore](../data/backup-and-restore.md) for full procedure.

### 11. Dependency & Security Review

```bash
# Check for outdated Python packages
cd Backoffice
pip list --outdated

# Check for Node package vulnerabilities (Backoffice JS toolchain)
npm audit
```

Report significant vulnerabilities to the development team. Do not upgrade packages without testing in staging first.

> Dependency audits outside `Backoffice/` are owned by other teams.

### 12. SSL Certificate Expiry Check

Verify TLS certificates for the production domain(s) are not expiring within 60 days. Azure App Service with managed certificates auto-renews, but custom certificates may require manual action.

### 13. WAF Rule Review

If Azure Application Gateway WAF is configured:
1. Review WAF logs for false-positive blocks on legitimate admin/form endpoints.
2. Confirm any rule exclusions added in previous quarters are still necessary and documented.
3. Check that new OWASP CRS updates have not introduced new false positives.

---

## Event-Driven Tasks (Do When Needed)

### After a Staff Change

- Deactivate departing user account (see [User & role management](user-and-role-management.md) §4).
- If they held Bearer JWT sessions: tokens expire on their normal lifetime, or coordinate `SECRET_KEY` rotation if immediate revocation is required for all sessions.
- Reassign any pending submissions or approvals they owned.

### After a Form Cycle Closes

1. Admin → Assignment Management → [assignment] → close the assignment (set status to Closed).
2. Export all submissions for archiving (Excel bulk export).
3. Approve or return any still-pending submissions.
4. Notify focal points that the cycle is closed.

### After Adding Countries or Indicators

- Run `flask sync-indicator-embeddings` to update AI search.
- Spot-check **Public Assignments** (Admin → Public Assignments) so intended indicators/countries are published as expected; downstream consumers may cache responses briefly.

### After Renaming a Matrix Column (Form Builder)

Matrix field cells are stored in `disagg_data` as `{row}_{column_name}`. Renaming a column's internal `name` in the form builder (not just its display label) leaves old cell keys behind in every row saved before the rename — they no longer match any row/column pairing, so they're silently excluded from the UI and totals, but stay in the JSON forever (e.g. `form_data.id=286867` had a lingering `"...NS 2025 Total Funding": 0` key after item 1403's column was renamed to `ns_fun`).

New saves are protected automatically (`app.utils.api_serialization.prune_stale_matrix_cell_keys`, wired into both the top-level and repeat-group matrix save paths, plus the client-side collector in `matrix-handler.js`). After a rename, clean up the **existing** rows:

```bash
cd Backoffice

# 1. Preview affected rows (safe, read-only)
python scripts/ops/prune_stale_matrix_cell_keys.py --form-item-id <ITEM_ID> --dry-run

# 2. Apply after reviewing the dry-run output
python scripts/ops/prune_stale_matrix_cell_keys.py --form-item-id <ITEM_ID> --force
```

Omit `--form-item-id` to scan every matrix item at once (still `--dry-run` first).

**On production** (no direct DB access — App Service is on private networking, see [Backup & restore](../data/backup-and-restore.md)). The repo root's `azure-webapp/` tooling opens an `az webapp create-remote-connection` SSH tunnel to the running container (which already has production's `DATABASE_URL` in its environment) and runs a command non-interactively — this is the same mechanism `azure_webapp_ssh.ps1` uses for interactive sessions:

1. Take a DB snapshot first if pruning a large number of rows (see [Maintenance window checklist](#maintenance-window-checklist-template)).
2. Requires `az login` (access to the target subscription) and the Windows OpenSSH client. From the repo root:
   ```powershell
   . .\azure-webapp\azure_webapp_config.ps1
   $t = Resolve-AzureWebAppEnvironment -Name PROD   # or STAGING

   # 1. Preview (safe, read-only)
   .\azure-webapp\azure_webapp_run.ps1 -WebApp $t.WebApp -ResourceGroup $t.ResourceGroup -Port $t.Port -Label $t.Label `
       -Command "cd /app && python scripts/ops/prune_stale_matrix_cell_keys.py --form-item-id <ITEM_ID> --dry-run"

   # 2. Apply after reviewing the dry-run output
   .\azure-webapp\azure_webapp_run.ps1 -WebApp $t.WebApp -ResourceGroup $t.ResourceGroup -Port $t.Port -Label $t.Label `
       -Command "cd /app && python scripts/ops/prune_stale_matrix_cell_keys.py --form-item-id <ITEM_ID> --force"
   ```
   Use `cd /app` (not `Backoffice/`) — that's the deployed app root inside the container (see `entrypoint.sh`). Omit `--form-item-id` to scan every matrix item. `--force` is preferred over the interactive confirmation prompt here since the SSH tunnel is a one-shot non-interactive command.

   Fallback with no local Azure CLI/OpenSSH: Azure Portal → App Service → **Development Tools → SSH** (browser-based Kudu console, no password needed) and run the same two commands from `/app`.
3. Re-run the `--dry-run` command — it should report "No stale matrix cell keys found" once cleanup is complete.

### After a Code Deployment

1. Confirm `python -m flask db heads` returns one head.
2. Run `python -m flask db upgrade` if the deployment includes migrations.
3. Rebuild CSS if templates changed: `npm run build:css` in `Backoffice/`.
4. Smoke test: login, load a form, check AI health endpoint.

Full checklist: [Release process](../development/release-process.md).

---

## Maintenance Window Checklist (Template)

Copy this into your incident/change management system for each planned maintenance window:

```
[ ] Notify users of downtime window (if applicable)
[ ] Take a DB snapshot immediately before starting
[ ] Confirm python -m flask db heads → single head
[ ] Run python -m flask db upgrade (if migrations included)
[ ] Rebuild CSS if templates changed (npm run build:css)
[ ] Restart / redeploy application
[ ] Smoke test: login, admin page, form load, AI health
[ ] Confirm python -m flask db current matches expected revision
[ ] Confirm no RBAC warnings in startup logs
[ ] Notify users window is complete
[ ] Document any issues encountered
```
