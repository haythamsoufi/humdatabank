# Persistent Translations

By default, translation `.po`/`.mo` files are baked into the Docker image at build time. Any edits made through the admin UI (`/admin/translations/manage`) live on the container's ephemeral filesystem and are lost when the container is replaced during a deployment.

The entrypoint automatically detects persistent storage and manages translations so each environment keeps its own independently.

## How It Works

```
┌──────────────────────────────────────────────────────────────┐
│ Dockerfile (build time)                                      │
│  1. Compile .po → .mo (working baseline baked into image)    │
│  2. Copy translations/ → translations_base/ (safe copy)     │
├──────────────────────────────────────────────────────────────┤
│ Container startup (entrypoint.sh)                            │
│                                                              │
│  1. Resolve TRANSLATIONS_PERSISTENT_PATH:                    │
│     ├─ Explicit env var? → use it                            │
│     ├─ /data/translations is a mount? → auto-detect          │
│     └─ Neither? → use image-baked translations (no-op)       │
│  2. Persistent path empty? → seed from translations_base     │
│     Persistent path has files? → merge new msgids,           │
│                                  keep admin edits            │
│  3. Compile all .po → .mo in persistent path                 │
│  4. Point translations/ at the persistent path               │
│     ├─ Docker volume at /app/translations? → already there   │
│     └─ Separate path (/data/translations)? → symlink         │
│  5. App starts — reads/writes go to persistent storage       │
└──────────────────────────────────────────────────────────────┘
```

**Merge logic** (per locale, per `msgid`):

| Scenario | Result |
|----------|--------|
| `msgid` in image AND persistent (non-empty `msgstr`) | Keep persistent `msgstr` (admin edits preserved) |
| `msgid` in image but NOT in persistent | Add with image's `msgstr` (new string from developer) |
| `msgid` in persistent but NOT in image | Mark obsolete (developer removed the string) |

## Azure App Service Setup

### 1. Create an Azure File Share

One share per environment keeps translations independent.

**Portal:** Storage Account → File shares → + File share

| Field | Value |
|-------|-------|
| Name | `translations-staging` (or `translations-prod`, etc.) |
| Tier | Transaction optimized |

**CLI:**

```bash
RG="your-resource-group"
STORAGE_ACCOUNT="yourstorageaccount"
SHARE_NAME="translations-staging"

az storage share-rm create \
  --resource-group "$RG" \
  --storage-account "$STORAGE_ACCOUNT" \
  --name "$SHARE_NAME" \
  --quota 1
```

### 2. Mount the Share in the Web App (Path Mapping)

**Portal (typical):** App Service → **Settings** → **Configuration** → **Path mappings** → + Add storage mount

Note: Azure Portal UI labels move around occasionally. If you don’t see “Configuration → Path mappings”, look for a “Storage”, “Path mappings”, or “Storage mounts” section under App Service settings.

| Field | Value |
|-------|-------|
| Name | `translations` |
| Type | Azure Files |
| Storage Account | *(your account)* |
| Share | `translations-staging` |
| Mount path | `/data/translations` |

**CLI:**

```bash
WEBAPP="your-webapp-name"

az webapp config storage-account add \
  --resource-group "$RG" \
  --name "$WEBAPP" \
  --custom-id translations \
  --storage-type AzureFiles \
  --account-name "$STORAGE_ACCOUNT" \
  --share-name "$SHARE_NAME" \
  --mount-path /data/translations \
  --access-key "$(az storage account keys list -g $RG -n $STORAGE_ACCOUNT --query '[0].value' -o tsv)"
```

### 3. Deploy

That's it. The entrypoint auto-detects the mount at `/data/translations`, seeds it on first boot, and preserves admin edits on subsequent deploys.

No env vars needed — the entrypoint uses `mountpoint` to detect the Azure Files share. If you prefer a custom path, set `TRANSLATIONS_PERSISTENT_PATH` in the Web App’s **Environment variables** (App settings) and restart the app.

See also: `docs/setup/azure-storage.md` for the broader Azure Storage setup (Blob uploads + Azure Files translations).

## Docker Compose (local development)

The `docker-compose.yml` is already configured with a named `translations_data` volume mounted at `/app/translations` and the `TRANSLATIONS_PERSISTENT_PATH` env var. Translations persist across `docker compose down && docker compose up` and across image rebuilds.

The host's `Backoffice/translations/` (git-tracked `.po` files) stays intact — the named volume is at `/app/translations` which is outside the `./Backoffice/app:/app/app` bind mount.

### Reset to git baseline

```bash
docker compose down -v  # removes named volumes including translations_data
docker compose up       # seeds fresh from the image baseline
```

## Operations

### Reset translations to the git baseline (Azure)

Delete the contents of the Azure File Share (Portal → Storage Account → File Shares → select share → delete contents), then restart the Web App. The next boot re-seeds from the image.

### Migrate existing translations before enabling persistence

If the running environment already has admin-edited translations you want to keep:

1. Go to `/admin/translations/manage` → **Export** → **PO ZIP** to download all locales.
2. Set up the Azure Files mount and deploy (first boot seeds from the image baseline).
3. Go to `/admin/translations/manage` → **Import** → upload the ZIP.
4. Click **Compile** to regenerate `.mo` files.

### Running without persistence

Leave `TRANSLATIONS_PERSISTENT_PATH` unset and don't mount anything at `/data/translations`. The app uses the image-baked translations as before. This is the default for plain `python run.py` local development.
