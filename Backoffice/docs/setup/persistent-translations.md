# Translation persistence

Admin edits made in `/admin/translations/manage` are stored in the **`translation_string`** table, so they survive container replacement the same way any other application data does. No file share or volume is involved.

The `.po`/`.mo` files are build artifacts. Each container rebuilds them at boot and keeps its own copy on ephemeral storage.

## How it works

```
┌──────────────────────────────────────────────────────────────┐
│ Dockerfile (build time)                                      │
│  Extract messages.pot from source, compile a baseline .mo    │
│  (the fallback if the boot rebuild cannot run)               │
├──────────────────────────────────────────────────────────────┤
│ Container startup (entrypoint.sh)                            │
│  1. flask db upgrade                                         │
│  2. flask translations compile-catalog                       │
│     messages.pot supplies the msgids                         │
│     translation_string supplies the values, falling back to  │
│     the catalog being replaced where it has no row           │
│     → writes translations/<locale>/LC_MESSAGES/messages.po   │
│     → compiles messages.mo                                   │
│     → records the catalog version in translations/           │
│       .catalog_version                                       │
├──────────────────────────────────────────────────────────────┤
│ While running                                                │
│  An admin edit writes translation_string, rebuilds this      │
│  container's artifacts, and bumps translation_catalog_version│
│  Every worker polls that counter, rebuilds when it is behind,│
│  and calls flask_babel.refresh()                             │
└──────────────────────────────────────────────────────────────┘
```

The counter is what makes this work across containers: a peer's edit never changes a local file's mtime, so the database is the only signal that reaches every replica.

## Requirements

- Run migrations on deploy so `translation_catalog_version` exists (`flask db upgrade`, which `entrypoint.sh` already does unless `SKIP_MIGRATIONS` is set).
- Nothing else. There is no mount to configure and no `TRANSLATIONS_PERSISTENT_PATH` setting.

## Migrating from the Azure Files share

Earlier deployments kept `.po` files on an Azure Files share mounted at `/data/translations`. Edits made there are not automatically in the database, so import them **before** deploying this change.

A rebuild falls back to the catalog it is replacing for any msgid the database has no row for, so an unpopulated database degrades to the translations baked into the image rather than erasing them. What that does **not** cover is any edit made on the share since the last time the catalogs were committed to the repository: those exist in neither the image nor the database, and the import below is the only thing that preserves them.

1. On the **currently running** version, load the share's catalogs into `translation_string`:

```bash
python -m flask translations import-catalog
```

   `import-catalog` is idempotent and never overwrites human-approved rows.

2. Confirm the rows landed — the Unreviewed tab on `/admin/translations/quality`, or:

```bash
python -m flask translations hygiene
```

3. Deploy this version and let the entrypoint rebuild the catalogs.

4. Once the deployment looks correct, remove the storage mount. On Azure App Service:

```bash
az webapp config storage-account delete \
  --resource-group "$RG" \
  --name "$WEBAPP" \
  --custom-id translations
```

   The Azure File Share itself can then be deleted. Keep it until you are satisfied the translations came through; it costs almost nothing and is the only copy of anything that failed to import.

If you would rather keep a portable backup first, `/admin/translations/manage` → **Export** → **PO ZIP** downloads every locale, and **Import** restores it.

## Operations

### Rebuild catalogs by hand

```bash
python -m flask translations compile-catalog            # all supported locales
python -m flask translations compile-catalog --locale fr
```

Useful if a container's artifacts are suspected stale and you do not want to wait for the poll interval, or after restoring `translation_string` from a backup.

### Reset translations to the repository baseline

Delete the relevant `translation_string` rows and rebuild; the catalogs fall back to the msgids and committed values shipped in the image. Prefer targeting a locale rather than truncating the table, since provenance and review status live there too.

### Local development

`python run.py` uses the catalogs in `Backoffice/translations/` directly and does not rebuild them at boot. Use the admin UI, or `scripts/i18n/extract_update_translations.py` when adding new strings.

**`compile-catalog` overwrites the git-tracked catalogs** with the contents of whatever database you are pointed at. Against an empty or scratch database that quietly replaces the committed translations with the same files minus every msgstr, which is easy to miss in a large diff. Point `BACKOFFICE_TRANSLATIONS_DIR` at a scratch directory before running it locally, and check `git status` afterwards.

See also: `docs/setup/azure-storage.md` for Azure Blob upload storage, which is unaffected by this.
