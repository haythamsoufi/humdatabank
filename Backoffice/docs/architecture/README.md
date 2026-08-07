# Backoffice database schema (architecture review)

Shareable exports of the IFRC Network Databank **Backoffice** PostgreSQL schema for architecture review, security assessment, and integration planning.

## Using the interactive HTML

1. Open [`database-schema.html`](database-schema.html) in a browser.
2. **Schema overview** — pinned at the top of the left nav; click it anytime to return to the relationship diagrams from a table detail view.
3. **Tables** — listed below by domain; click a table name for columns, FKs, and a local relationship graph.
4. **Diagram tabs** — Full schema (default), Domain map, Core data flow, Key tables.
5. **Deep links** — `#overview=full`, `#overview=domain`, `#table=form_data`.

## Files

| File | Best for |
|------|----------|
| [`database-schema.html`](database-schema.html) | **Interactive review** — opens with a full ER-style graph (all tables + FKs), plus domain map, core flow, and key-table views; pan/zoom, search, FK navigation. |
| [`database-schema.md`](database-schema.md) | Human review — domain overview, design patterns, per-table column/FK reference. Export to PDF via Word, Pandoc, or GitHub print. |
| [`database-schema-catalog.csv`](database-schema-catalog.csv) | Excel / Power BI — filter and pivot by domain, table, or column. |
| [`database-schema-ddl.sql`](database-schema-ddl.sql) | DBAs and tooling — approximate `CREATE TABLE` DDL from SQLAlchemy models. |
| [`background-jobs-and-progress-ui.md`](background-jobs-and-progress-ui.md) | **Reusable pattern** — server-side batch/single-entity jobs, cross-worker locks, progress banner UI, agent migration checklist (reference: AI Documents). |

## Regenerate

From `Backoffice/`:

```bash
python scripts/dev/export_database_schema.py
```

Optional output directory:

```bash
python scripts/dev/export_database_schema.py --output-dir docs/architecture
```

## Authoritative DDL from a live database

For production-identical DDL (extensions, indexes, constraints from all migrations):

```bash
pg_dump --host=<host> --username=<user> --dbname=<db> \
  --schema-only --no-owner --no-privileges \
  -f database-schema-live.sql
```

See [backup-and-restore runbook on GitHub](https://github.com/IFRC-C2/IFRCNetworkDatabank/blob/main/Backoffice/docs/runbooks/data/backup-and-restore.md).

## Source of truth

- **Repository:** [IFRC-C2/IFRCNetworkDatabank](https://github.com/IFRC-C2/IFRCNetworkDatabank)
- **Models:** [`Backoffice/app/models/`](https://github.com/IFRC-C2/IFRCNetworkDatabank/tree/main/Backoffice/app/models)
- **Migrations:** [`Backoffice/migrations/versions/`](https://github.com/IFRC-C2/IFRCNetworkDatabank/tree/main/Backoffice/migrations/versions) (Flask-Migrate / Alembic)
- **Architecture notes:** [DEVELOPER-HANDBOOK.md — Database Architecture](https://github.com/IFRC-C2/IFRCNetworkDatabank/blob/main/docs/DEVELOPER-HANDBOOK.md)
