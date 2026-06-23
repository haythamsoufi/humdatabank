#!/usr/bin/env bash
# Upload Backoffice/app/static to the Azure Blob "static" container.
#
# Used by GitHub Actions (deploy-to-webapp.yml) and can be run locally:
#   export AZURE_STORAGE_CONNECTION_STRING="..."
#   ./Backoffice/azure/upload-static-assets.sh
#
# Optional env:
#   STATIC_BLOB_CONTAINER      default: static  (use static-staging for staging app)
#   STATIC_SOURCE_DIR            default: Backoffice/app/static (relative to repo root)
#   STATIC_CONFIGURE_CORS=1      one-time: set blob CORS (account-level; do not run every deploy)
#   STATIC_CORS_ORIGINS          space-separated origins when STATIC_CONFIGURE_CORS=1

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

echo "Uploading static assets from ${SOURCE_DIR} ..."
az storage blob upload-batch \
  --destination "${CONTAINER}" \
  --source "${SOURCE_DIR}" \
  --connection-string "${AZURE_STORAGE_CONNECTION_STRING}" \
  --content-cache-control "${CACHE_CONTROL}" \
  --overwrite \
  --output none

ACCOUNT_NAME="$(az storage account show \
  --connection-string "${AZURE_STORAGE_CONNECTION_STRING}" \
  --query name -o tsv)"
STATIC_CDN_URL="https://${ACCOUNT_NAME}.blob.core.windows.net/${CONTAINER}"

echo "OK: static assets uploaded."
echo "STATIC_CDN_URL=${STATIC_CDN_URL}"
