# Azure Storage on App Service

This guide covers two separate Azure Storage mechanisms used by this repo:

1. **Azure Blob Storage** — for all user-uploaded files (documents, resources, logos, AI documents, etc.)
2. **Azure Files (Path Mappings)** — for persistent translation files mounted into the container

These are independent services. Blob Storage is accessed via the Azure SDK; Path Mappings are filesystem mounts managed by App Service.

---

## Azure Blob Storage for Uploads

All user-uploaded files (admin documents, resources, publications, form submission documents, sector/subsector logos, AI Knowledge Base documents) are stored in **Azure Blob Storage** when the `AZURE_STORAGE_CONNECTION_STRING` environment variable is set. Without it, the app falls back to writing files under the local `UPLOAD_FOLDER` directory (suitable for local development only).

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
| `system` | `system/sectors/`, `system/subsectors/` | Sector and subsector logos |
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

## Azure Files (Path Mappings) for Translations

This section explains how to mount **Azure Files** into an **Azure App Service Web App** (Linux / container) using **Path mappings** for **persistent translations**.

### When to use Path mappings

Use Path mappings when you need **durable files** that must survive:

- container restarts
- slot swaps
- redeployments (new image)

Examples in this repo:

- **Translations**: mount a file share to `/data/translations` so each environment (staging/prod) maintains its own `.po`/`.mo` files.

### Basic vs Advanced mode in the Portal

- **Basic**: the portal provides dropdown pickers and fills most fields for you.
- **Advanced**: you type values explicitly and can use **Key Vault references** instead of pasting storage keys.

Different apps can show different defaults depending on tenant policy, Key Vault integration, or portal UI changes.

### What to enter (Azure Files)

In **Web App → Settings → Configuration → Path mappings → Add storage mount**:

- **Storage type**: Azure Files
- **Protocol**: SMB (typical default)
- **Account name**: the **Storage Account name** that contains the File Share (e.g. `databankprodsa`)
- **Share name**: the **File Share name** inside that Storage Account (e.g. `translations-prod`)
- **Mount path**: the absolute path inside the container (for this repo: **`/data/translations`**)

#### Storage access

You'll usually see one of these options:

- **Manual input**: paste a Storage Account access key (Storage Account → Access keys → key1/key2).
- **Key Vault reference**: select an App Setting whose value is a Key Vault reference.

##### If using Key Vault reference

1. Create a Key Vault secret whose value is the **Storage Account access key**.
2. In the Web App, create an App Setting that references it:

   `@Microsoft.KeyVault(SecretUri=https://<vault>.vault.azure.net/secrets/<secret-name>/<version>)`

3. In the storage mount dialog, choose that App Setting in the **App settings** dropdown.

### Translation persistence in this repo

Backoffice translation source files live at:

- `Backoffice/translations/<lang>/LC_MESSAGES/messages.po`
- `Backoffice/translations/messages.pot`

At runtime, the container uses `/app/translations` as the active translations directory.

If you mount Azure Files at `/data/translations`, the container entrypoint:

- detects the mount
- syncs/merges from the image baseline
- compiles `.po → .mo`
- points `/app/translations` to the mounted directory

This makes translations **environment-owned**:

- staging edits stay in staging
- production edits stay in production

### Recommended setup per environment

- Create **one File Share per environment**, e.g.:
  - `translations-staging`
  - `translations-prod`
- Mount it to the same in-container path for both environments:
  - `/data/translations`

### Troubleshooting

- **Mount path is empty after deploy**: confirm the mount exists in **Path mappings** and you clicked **Save** on Configuration.
- **Permissions / access failures**: verify the access key (or Key Vault reference) is correct and the Web App identity can read the secret.
- **Translations still "reset" on deploy**: ensure you mounted **Azure Files** to `/data/translations` (not a different path), or explicitly set `TRANSLATIONS_PERSISTENT_PATH` to your chosen mount path.
