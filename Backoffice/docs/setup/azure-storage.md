# Azure Storage on App Service

This guide covers **Azure Blob Storage**, used for all user-uploaded files (documents, resources, logos, AI documents, etc.).

Translations previously needed an **Azure Files** path mapping as well. They no longer do — see [Azure Files (Path Mappings) for Translations — removed](#azure-files-path-mappings-for-translations--removed) at the end of this guide if your Web App still has that mount.

---

## Azure Blob Storage for Uploads

All user-uploaded files (admin documents, resources, publications, form submission documents, sector logos, AI Knowledge Base documents) are stored in **Azure Blob Storage** when the `AZURE_STORAGE_CONNECTION_STRING` environment variable is set. Without it, the app falls back to writing files under the local `UPLOAD_FOLDER` directory (suitable for local development only).

### Why Blob Storage instead of local disk?

App Service local storage is **ephemeral** — files are lost on redeployment, container restart, or scale-out. Even with `WEBSITES_ENABLE_APP_SERVICE_STORAGE=true`, the `/home` mount has performance limitations and is not designed for high-throughput file I/O. Azure Blob Storage provides durable, scalable, and cost-effective object storage that persists independently of the App Service lifecycle.

### Architecture

The application uses a storage abstraction layer (`app/services/storage_service.py`) that routes all file I/O through one of two providers:

| Provider | Selected when | Writes to |
|----------|--------------|-----------|
| `azure_blob` | `AZURE_STORAGE_CONNECTION_STRING` is set | Azure Blob container (default: `uploads`) |
| `filesystem` | No connection string (local dev) | `UPLOAD_FOLDER` on disk |

Files are organised by category as blob prefixes (or subdirectories on local disk):

| Category | Blob prefix | Content |
|----------|-------------|---------|
| `admin_documents` | `admin_documents/` | Standalone uploaded documents and their thumbnails |
| `resources` | `resources/` | Resource and publication files (multilingual) |
| `submissions` | `submissions/` | Form submission document uploads |
| `system` | `system/sectors/` | Sector logos |
| `pb_progress` | `pb_progress/` | P&B Progress Excel source, build status, and generated report outputs |

When `STATIC_CDN_URL` is set and uploads use Azure Blob, sector logos are also mirrored into the public static blob container at `system/sectors/` so browsers load them from the CDN instead of the Flask app. After enabling CDN on an existing deployment, run `flask sync-sector-logos-cdn` once to backfill logos uploaded before mirroring was enabled.
| `ai_documents` | `ai_documents/` | AI Knowledge Base uploaded files |

### Required environment variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `AZURE_STORAGE_CONNECTION_STRING` | Yes (on Azure) | *(empty — filesystem mode)* | Storage Account connection string |
| `AZURE_STORAGE_CONTAINER` | No | `uploads` | Blob container name |
| `UPLOAD_STORAGE_PROVIDER` | No | *(auto-detected)* | Force `filesystem` or `azure_blob` |

### Setup steps

1. **Get the connection string** from your Storage Account:
   - Azure Portal → Storage account → **Security + networking** → **Access keys** → copy **Connection string** from key1
   - Or via CLI: `az storage account show-connection-string --name <ACCOUNT> --resource-group <RG> --output tsv`

2. **Add it to the App Service** environment variables:
   - Azure Portal → App Service → **Settings** → **Environment variables** → **App settings** tab → **+ Add**
   - Name: `AZURE_STORAGE_CONNECTION_STRING`, Value: *(the connection string)*
   - Name: `AZURE_STORAGE_CONTAINER`, Value: `uploads`
   - Click **Apply** and confirm the restart

3. **Verify the `uploads` container exists** in your Storage Account:
   - Azure Portal → Storage account → **Data storage** → **Containers** → confirm `uploads` is listed
   - If missing: create it with **Private** access level
   - Or via CLI: `az storage container create --name uploads --connection-string "$CONN_STR" --public-access off`

4. **Deploy the updated code** and upload a test document to verify blobs appear in the container.

### Migrating existing local files

If the App Service already has files on local disk that need to be preserved, upload them to blob storage from the App Service SSH console (Kudu):

```bash
az storage blob upload-batch \
    --destination uploads \
    --source /home/site/wwwroot/uploads/ \
    --connection-string "$AZURE_STORAGE_CONNECTION_STRING" \
    --overwrite false
```

### Local development

No Azure setup is needed for local development. When `AZURE_STORAGE_CONNECTION_STRING` is not set (the default in `.env`), the app uses the local `UPLOAD_FOLDER` directory automatically. Files are stored in the same category subdirectory structure (`admin_documents/`, `resources/`, etc.).

### Relationship to `WEBSITES_ENABLE_APP_SERVICE_STORAGE`

`WEBSITES_ENABLE_APP_SERVICE_STORAGE` controls the built-in `/home` mount on App Service. It is **unrelated** to Azure Blob Storage. You can keep it set to `false` — the app no longer depends on `/home` persistence for uploads since they go directly to Blob Storage via the SDK.

---

## Azure Files (Path Mappings) for Translations — removed

Translations no longer use a file mount. Admin edits are stored in the
`translation_string` table and each container rebuilds its own `.po`/`.mo` files
at boot, so they persist across restarts, slot swaps, and redeployments the same
way the rest of the application data does.

If your Web App still has a storage mount at `/data/translations`, it is unused.
Follow the migration steps in
[`persistent-translations.md`](persistent-translations.md) — which import any
share-only edits into the database before you remove the mount — and then:

```bash
az webapp config storage-account delete \
  --resource-group "$RG" \
  --name "$WEBAPP" \
  --custom-id translations
```

Blob Storage for uploads, described above, is a different mechanism and is
unaffected.
