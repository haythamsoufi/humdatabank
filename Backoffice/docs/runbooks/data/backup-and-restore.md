# Backup and Restore

Disaster-recovery procedures for the Backoffice. Adapt schedules, retention, and RTO/RPO targets to your organisational policy — this document focuses on what the application depends on and how to verify a restore.

---

## 1. What Needs to Be Backed Up

| Asset | Where it lives | Criticality |
|-------|---------------|-------------|
| PostgreSQL database | Managed Postgres or self-hosted | **Critical** — all form data, users, submissions, AI documents |
| Uploaded files / document library | Azure Files or local disk | **High** — publications, resources, PDF attachments |
| Translation files | Azure Files (persistent) or local | **Medium** — regeneratable but time-consuming |
| App Service configuration / env vars | Azure Key Vault / App Service settings | **High** — secrets and keys; back up the *inventory* and *rotation procedures*, not the values themselves |
| Application code | Git repository | Covered by version control — not separately backed up |

---

## 2. PostgreSQL Backup

### Logical backup (pg_dump)

Schedule daily logical backups. Store encrypted and off-server:

```bash
# Full database dump (run as postgres user or with appropriate credentials)
pg_dump \
  --host=<host> \
  --port=5432 \
  --username=<user> \
  --dbname=<dbname> \
  --format=custom \
  --file=backup_$(date +%Y%m%d_%H%M%S).dump

# Compress and encrypt before storing off-server:
gpg --symmetric --cipher-algo AES256 backup_<timestamp>.dump
```

**Retention recommendation:** Daily for 30 days; weekly for 90 days; monthly for 1 year.

### Point-in-time recovery (PITR)

If your hosting provides managed PostgreSQL (Azure Database for PostgreSQL, AWS RDS, etc.), enable PITR / WAL archiving for RPO < 1 hour. This provides granular recovery to any point in the retention window.

**Azure Database for PostgreSQL:** PITR is enabled by default; retention window configurable (7–35 days on General Purpose tier).

### Azure Flexible Server restore and private networking

When you **restore** from an Azure backup (point-in-time restore, geo-redundant restore, or equivalent), Azure provisions a **new** Flexible Server resource — it is not always an in-place repair on the original hostname.

In typical IFRC-style setups the database tier is **not internet-facing**: access is via **private connectivity only** (Virtual Network integration, private DNS, and **private endpoints**).

**Why this matters for every restore:**

1. The **new server** gets new identifiers (FQDN, resource ID). **`DATABASE_URL` in App Service (or Key Vault) must be updated** once the restore completes and credentials/endpoints are known.
2. **Private endpoints are tied to the server instance.** After a restore creates a new server, existing private endpoints **do not automatically move** to it. The **infrastructure team must recreate or reconfigure private endpoints** (and any associated Private DNS zone records / VNet links) so workloads such as App Service (via VNet integration or private endpoint to the DB subnet path your architecture uses) can reach PostgreSQL again.
3. Until networking is fixed, the application will fail with connection errors even if the data restore succeeded — this is **not** an application bug.

**Runbook expectation:** Treat DB restore as a **joint app + infra** change: open an infra ticket early; do not assume the app team can complete DR alone when private endpoints are required.

After infra confirms connectivity from the app subnet, proceed with [§6 Post-restore verification](#6-post-restore-verification-checklist) and update secrets inventory.

### Verifying the backup (quarterly)

Use **`pg_dump` / `pg_restore`** when you manage backups yourself (e.g. logical dumps to blob storage). For **Azure Flexible Server restore scenarios** that provision a **new** server, follow **§2 — Azure Flexible Server restore and private networking** above before relying on connectivity from App Service.

```bash
# 1. Restore to a scratch / staging Postgres instance
pg_restore \
  --host=<staging-host> \
  --port=5432 \
  --username=<user> \
  --dbname=<dbname> \
  --format=custom \
  backup_<timestamp>.dump

# 2. Connect and verify pgvector extension is present
psql -h <staging-host> -U <user> -d <dbname> -c "\dx"
# Should list vector extension

# 3. Run migration check
cd Backoffice
DATABASE_URL=postgresql://<user>:<pass>@<staging-host>/<dbname> python -m flask db current
# Must return the expected revision
```

---

## 3. Uploaded Files and Document Library

If document uploads are stored on **Azure Files** (mounted volume):

- Azure Files: enable Azure Backup vault for the file share. Schedule daily snapshots.
- Alternatively: sync the mount to Azure Blob Storage with `azcopy sync` on a schedule.

```bash
# Example: sync mounted volume to blob storage
azcopy sync \
  "/mnt/backoffice-files" \
  "https://<storage-account>.blob.core.windows.net/<container>" \
  --recursive
```

**If uploads are on ephemeral local disk (not mounted):** Uploads will be lost on any restart or scale-out. This is not suitable for production — configure a persistent mount or Azure Files.

See: [`../../setup/azure-storage.md`](../../setup/azure-storage.md) and [`../../setup/persistent-translations.md`](../../setup/persistent-translations.md).

---

## 4. Local Development Database

**PostgreSQL is required for all environments including local development** — there is no SQLite fallback. The application uses PostgreSQL-specific features (`JSONB`, `pgvector`, FTS GIN indexes) that are incompatible with SQLite.

Back up your local development database the same way as any PostgreSQL instance:
```bash
pg_dump -h localhost -U app hum_databank > backup_local.sql
```

See [Flask-Migrate & pgvector](flask-migrate-and-pgvector.md) §4 for a Docker quickstart to run PostgreSQL locally.

---

## 5. Secrets and Configuration Inventory

Do not store secret values in git. Back up:

- An **inventory** of which secrets exist and what they configure.
- **Rotation procedures** for each secret (how to generate a new value, where to update it, what downstream systems depend on it).
- Key Vault access policies (who can read/rotate each secret).

**Secrets that, if lost, require coordinated rotation:**
- `SECRET_KEY` — invalidates all browser sessions and JWTs signed with the prior key
- `DATABASE_URL` — app cannot start without this; **after an Azure Flexible Server restore** the hostname often changes — update this only after infra has recreated private endpoints and validated connectivity (see **§2 — Azure Flexible Server restore and private networking**, above)
- `OPENAI_API_KEY` — AI features stop working
- Credentials for outbound notification delivery (if configured) — notification sends fail until updated
- SMTP credentials — email notifications stop

---

## 6. Post-Restore Verification Checklist

Run after any restore operation (full or partial):

```bash
# 1. Confirm migration revision matches expected
python -m flask db current
# Compare with the revision from before the incident

# 2. Confirm single migration head
python -m flask db heads
# Must be exactly ONE head

# 3. Confirm pgvector extension is functional
python -m flask db upgrade  # should report "already up to date" or apply pending migrations safely

# 4. Smoke test: login
# Open browser → login as System Manager → admin dashboard loads

# 5. Smoke test: one read-only admin page
# Admin → User Management (or Countries) → list loads with expected data

# 6. Smoke test: one write path
# Admin → edit an existing record → save → confirm saved

# 7. AI health check
# GET /api/ai/v2/health → { "status": "ok", "rag_enabled": true }

# 8. RAG sanity check
# Send a test chat message that requires document search → confirm a response is returned
```

**After a restore from an older snapshot:**
- Any data entered after the snapshot time is lost — communicate this clearly to focal points.
- Re-open any AES assignments that were in progress at restore time if needed.
- If the restored DB is behind the current code's migration revision: run `flask db upgrade` to apply the forward migrations.

---

## 7. Recovery Time Objectives (Guidance)

| Scenario | Target RTO | Approach |
|----------|-----------|---------|
| Config change rollback | < 5 min | Revert App Service setting |
| Code rollback (no migration) | < 10 min | Slot swap |
| DB restore from snapshot (same day) | < 30 min | pg_restore from daily backup (self-hosted or reachable host) |
| DB restore with PITR | < 1 hr | Managed Postgres PITR |
| **Azure Flexible Server restore + private endpoints** | **Hours (plan with infra)** | New server instance → **infra recreates private endpoint / DNS** → app team updates `DATABASE_URL` → smoke tests — see **§2 — Azure Flexible Server restore and private networking** |
| Full disaster recovery (new environment) | 2–4 hrs | Provision → restore DB → restore files → configure secrets (often overlaps Flexible Server networking steps above) |

> Validate these targets annually with a DR drill.
