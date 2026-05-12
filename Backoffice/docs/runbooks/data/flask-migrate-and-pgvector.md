# Flask-Migrate, schema, and pgvector

Database change workflow for Backoffice. **PostgreSQL is required for all environments** (development, staging, production, testing) — there is no SQLite fallback. The application uses PostgreSQL-specific features including `JSONB` columns, `pgvector` for AI embeddings, and full-text search GIN indexes that are incompatible with SQLite.

---

## 1. Single-head policy (mandatory)

Before **creating** or **applying** migrations:

```bash
cd Backoffice
python -m flask db heads
```

You must see **exactly one** head revision. If multiple heads appear, merge or resolve the branch **before** `db migrate` / `db upgrade`.

---

## 2. Applying migrations

```bash
python -m flask db upgrade
```

Run as part of every deploy that ships model changes. Never hand-edit production schema without a matching migration in `migrations/versions/`.

---

## 3. PostgreSQL + pgvector (AI / RAG)

- AI document and indicator embeddings require pgvector-enabled Postgres and migrations that create vector columns and indexes (HNSW/IVFFlat per migration history).
- Changing **`AI_EMBEDDING_DIMENSIONS`** or embedding model without a column migration **will break similarity search**. Plan: migrate column → re-embed corpus. See [`../../setup/ai-configuration.md`](../../setup/ai-configuration.md).

---

## 4. Local Development Database

**PostgreSQL is required even for local development.** Run a local PostgreSQL instance using Docker or a native install:

```bash
# Quickstart with Docker (from repo root or Backoffice/)
docker run -d \
  --name hum-databank-db \
  -e POSTGRES_USER=app \
  -e POSTGRES_PASSWORD=app \
  -e POSTGRES_DB=hum_databank \
  -p 5432:5432 \
  pgvector/pgvector:pg16

# Set DATABASE_URL in Backoffice/.env
DATABASE_URL=postgresql+psycopg2://app:app@localhost:5432/hum_databank
```

The `pgvector/pgvector` image includes the pgvector extension pre-installed. Alternatively use the default `postgres:16` image and run `CREATE EXTENSION vector;` manually after connecting.

---

## 5. Indicator Bank embeddings

Operational command (after Indicator Bank edits in production workflows):

```bash
python -m flask sync-indicator-embeddings
```

See [`../ai/indicator-resolution.md`](../ai/indicator-resolution.md).

---

## Related

- Backup expectations: [`backup-and-restore.md`](backup-and-restore.md)
- Incident triage when migrations fail: [`../incidents/general-incident-triage.md`](../incidents/general-incident-triage.md)
