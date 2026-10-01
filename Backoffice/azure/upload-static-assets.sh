#!/usr/bin/env bash
# Upload Backoffice/app/static to an Azure Blob container (static / static-staging).
#
# Used by GitHub Actions (deploy-to-webapp.yml) and can be run locally:
#   export AZURE_STORAGE_CONNECTION_STRING="..."
#   ./Backoffice/azure/upload-static-assets.sh
#
# Upload strategy:
#   AzCopy copy in two passes so Cache-Control is set during the upload
#   (azcopy sync and set-properties cannot set this HTTP header):
#     *.js / *.css → must-revalidate
#     everything else → long-lived immutable
#   One `az storage blob update` per file is much slower (~6 min for ~500
#   JS/CSS files, mostly CLI startup). These copies move ~30MB in under a minute.
#   az storage blob upload-batch — fallback when AzCopy is not installed.
#
# Optional env:
#   STATIC_BLOB_CONTAINER            default: static  (use static-staging for staging app)
#   STATIC_SOURCE_DIR                default: Backoffice/app/static
#   STATIC_STORAGE_ACCOUNT_NAME      override AccountName parsed from connection string
#   STATIC_CONFIGURE_CORS=1          one-time blob CORS setup (account-level)
#   STATIC_CORS_ORIGINS              space-separated origins when STATIC_CONFIGURE_CORS=1

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
SOURCE_DIR="${STATIC_SOURCE_DIR:-${REPO_ROOT}/Backoffice/app/static}"
CONTAINER="${STATIC_BLOB_CONTAINER:-static}"
# Blob metadata can't vary by request query string the way the Flask static route
# does (see app/static_serving.py): a blob at js/forms/modules/foo.js is the same
# object whether a client asks for it with ?v=... or bare. Pages must request a
# new ?v= (deploy token + content hash from static_url() / the forms import map)
# when a file changes — already-cached Cache-Control: immutable responses are
# never revalidated. CSS/JS can also be reached bare via a missed import map, so
# they get must-revalidate for *new* fetches. That header is rewritten on every
# deploy (even when AzCopy dry-run finds no byte changes) so existing blobs do
# not keep a year-long immutable policy.
CACHE_CONTROL="max-age=31536000, public, immutable"
CACHE_CONTROL_REVALIDATE="max-age=0, public, must-revalidate"

if [[ -z "${AZURE_STORAGE_CONNECTION_STRING:-}" ]]; then
  echo "ERROR: AZURE_STORAGE_CONNECTION_STRING is not set." >&2
  exit 1
fi

if [[ ! -d "${SOURCE_DIR}" ]]; then
  echo "ERROR: Static source directory not found: ${SOURCE_DIR}" >&2
  exit 1
fi

SOURCE_DIR="$(cd "${SOURCE_DIR}" && pwd)"

ACCOUNT_NAME="${STATIC_STORAGE_ACCOUNT_NAME:-}"
if [[ -z "${ACCOUNT_NAME}" ]]; then
  ACCOUNT_NAME="$(echo "${AZURE_STORAGE_CONNECTION_STRING}" | sed -n 's/.*AccountName=\([^;]*\).*/\1/p')"
fi
if [[ -z "${ACCOUNT_NAME}" ]]; then
  echo "ERROR: could not determine storage account name from connection string." >&2
  exit 1
fi

echo "Creating blob container '${CONTAINER}' (public read) if missing..."
az storage container create \
  --name "${CONTAINER}" \
  --connection-string "${AZURE_STORAGE_CONNECTION_STRING}" \
  --public-access blob \
  --output none 2>/dev/null || true

# ES module imports from blob URLs require CORS on the storage account (configure once).
if [[ "${STATIC_CONFIGURE_CORS:-}" == "1" && -n "${STATIC_CORS_ORIGINS:-}" ]]; then
  echo "Configuring blob CORS for origins: ${STATIC_CORS_ORIGINS}"
  az storage cors clear \
    --services b \
    --connection-string "${AZURE_STORAGE_CONNECTION_STRING}" \
    --output none || true
  # shellcheck disable=SC2086
  az storage cors add \
    --services b \
    --methods GET HEAD OPTIONS \
    --origins ${STATIC_CORS_ORIGINS} \
    --allowed-headers "*" \
    --exposed-headers "Content-Length,Content-Type,ETag,Content-MD5" \
    --max-age 86400 \
    --connection-string "${AZURE_STORAGE_CONNECTION_STRING}" \
    --output none
fi

# copy (not sync) so --cache-control is applied during upload. Quoted
# "${SOURCE_DIR}/*" is passed to AzCopy (not expanded by bash) so files
# land at the container root. Two passes (include/exclude-pattern match
# filename only, not path) so .js/.css get the revalidate header instead of
# a year-long immutable one — see CACHE_CONTROL_REVALIDATE comment above.
# overwrite=true rewrites the header even when the bytes already match.
_azcopy_copy_with_cache_control() {
  local dest="$1"
  echo "Uploading static assets with AzCopy (Cache-Control set during copy) ..."
  azcopy copy "${SOURCE_DIR}/*" "${dest}" \
    --recursive \
    --overwrite=true \
    --include-pattern="*.js;*.css" \
    --cache-control="${CACHE_CONTROL_REVALIDATE}" \
    --log-level=WARNING \
    --output-type=text
  azcopy copy "${SOURCE_DIR}/*" "${dest}" \
    --recursive \
    --overwrite=true \
    --exclude-pattern="*.js;*.css" \
    --cache-control="${CACHE_CONTROL}" \
    --log-level=WARNING \
    --output-type=text
}

_upload_with_azcopy() {
  local sas expiry dest
  expiry="$(date -u -d "+2 hours" '+%Y-%m-%dT%H:%MZ' 2>/dev/null || date -u -v+2H '+%Y-%m-%dT%H:%MZ')"
  sas="$(az storage container generate-sas \
    --name "${CONTAINER}" \
    --permissions acwrl \
    --expiry "${expiry}" \
    --connection-string "${AZURE_STORAGE_CONNECTION_STRING}" \
    -o tsv)"
  dest="https://${ACCOUNT_NAME}.blob.core.windows.net/${CONTAINER}?${sas}"
  _azcopy_copy_with_cache_control "${dest}"
}

_upload_with_az_cli() {
  # Fallback only (CI always installs AzCopy — see deploy-to-webapp.yml). upload-batch
  # has no per-pattern --cache-control, so every file gets the revalidate policy here
  # rather than risk immutable-caching a bare .js/.css URL — see CACHE_CONTROL_REVALIDATE
  # comment above. Costs images/fonts an extra conditional GET in this rarely-used path.
  echo "Syncing static assets with az storage blob upload-batch (fallback; use AzCopy for faster CI) ..."
  az storage blob upload-batch \
    --destination "${CONTAINER}" \
    --source "${SOURCE_DIR}" \
    --connection-string "${AZURE_STORAGE_CONNECTION_STRING}" \
    --content-cache-control "${CACHE_CONTROL_REVALIDATE}" \
    --max-connections 32 \
    --overwrite \
    --only-show-errors \
    --output none
}

if command -v azcopy >/dev/null 2>&1; then
  _upload_with_azcopy
else
  _upload_with_az_cli
fi

STATIC_CDN_URL="https://${ACCOUNT_NAME}.blob.core.windows.net/${CONTAINER}"

echo "OK: static assets uploaded."
echo "STATIC_CDN_URL=${STATIC_CDN_URL}"
