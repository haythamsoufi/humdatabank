# Backoffice database migrations (Flask-Migrate / Alembic)

Migrations live in `versions/`. Run from the `Backoffice` directory (see root `CLAUDE.md` for `FLASK_APP` and **`python -m flask db heads`** before creating migrations).

---

## TODO: Collapse to a single baseline migration (optional housekeeping)

**Goal:** Replace the long linear chain with one “initial” migration for a cleaner history, without losing production data.

### Preconditions

- [ ] Confirm **single Alembic head** (`python -m flask db heads`).
- [ ] Baseline migration’s `upgrade()` must match the **full current schema** (for **new** empty databases).
- [ ] For **existing** databases, schema must **already** match that baseline before stamping—stamping does not apply DDL.

### Implementation outline

- [ ] Generate or author one migration (e.g. `revision = "…"`, `down_revision = None`) that creates the complete schema from empty DB—or document why it is a no-op if you use another bootstrap path.
- [ ] Remove superseded files under `versions/` in a dedicated PR (coordinate with team: everyone must pull and reset local DB or stamp).
- [ ] **New installs:** `flask db upgrade` runs the single migration end-to-end.
- [ ] **Existing deployed DBs:** do **not** run `upgrade` if it would recreate existing objects. After verifying schema parity, **stamp** each database to the new revision, e.g. `flask db stamp <revision_id>` (or equivalent `UPDATE` on `alembic_version`), using the **revision id from the deployed codebase**.
- [ ] Repeat stamp for **staging**, **production**, and any long-lived **dev/shared** databases; document the revision id in release notes.
- [ ] Update CI / onboarding docs if they assume multiple migration steps.

### Risks

- Wrong stamp → silent schema drift until runtime errors.
- Running `upgrade` on an old DB after squash without stamping → duplicate DDL errors.
- Local developers mid-chain need a clear story (fresh DB, or stamp once).
