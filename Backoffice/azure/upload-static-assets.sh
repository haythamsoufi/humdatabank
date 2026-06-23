#!/usr/bin/env bash
# Upload Backoffice/app/static to an Azure Blob container (static / static-staging).
#
# Used by GitHub Actions (deploy-to-webapp.yml) and can be run locally:
#   export AZURE_STORAGE_CONNECTION_STRING="..."
#   ./Backoffice/azure/upload-static-assets.sh
#
# Upload strategy (fastest available):
#   1. AzCopy sync  — parallel transfers; on re-deploy only changed files are uploaded
#   2. az storage blob upload-batch — fallback when AzCopy is not installed
#
# Optional env:
#   STATIC_BLOB_CONTAINER        default: static  (use static-staging for staging app)
#   STATIC_SOURCE_DIR              default: Backoffice/app/static
#   STATIC_STORAGE_ACCOUNT_NAME    override AccountName parsed from connection string
#   STATIC_CONFIGURE_CORS=1          one-time blob CORS setup (account-level)
#   STATIC_CORS_ORIGINS            space-separated origins when STATIC_CONFIGURE_CORS=1

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
SOURCE_DIR="${STATIC_SOURCE_DIR:-${REPO_ROOT}/Backoffice/app/static}"
CONTAINER="${STATIC_BLOB_CONTAINER:-static}"
CACHE_CONTROL="max-age=31536000, public, immutable"

if [[ -z "${AZURE_STORAGE_CONNECTION_STRING:-}" ]]; then
  echo "ERROR: AZURE_STORAGE_CONNECTION_STRING is not set." >&2
  exit 1
fi

if [[ ! -d "${SOURCE_DIR}" ]]; then
  echo "ERROR: Static source directory not found: ${SOURCE_DIR}" >&2
  exit 1
fi

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

  echo "Syncing static assets with AzCopy (parallel; skips unchanged files) ..."
  # Trailing slash on source: sync contents of the directory into the container root.
  azcopy sync "${SOURCE_DIR}/" "${dest}" \
    --recursive \
    --delete-destination=false \
    --cache-control "${CACHE_CONTROL}" \
    --log-level=WARNING \
    --output-type=text
}

_upload_with_az_cli() {
  echo "Syncing static assets with az storage blob upload-batch (fallback; use AzCopy for faster CI) ..."
  az storage blob upload-batch \
    --destination "${CONTAINER}" \
    --source "${SOURCE_DIR}" \
    --connection-string "${AZURE_STORAGE_CONNECTION_STRING}" \
    --content-cache-control "${CACHE_CONTROL}" \
    --max-connections 32 \
    --overwrite \
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
