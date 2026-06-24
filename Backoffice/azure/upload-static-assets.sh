#!/usr/bin/env bash
# Upload Backoffice/app/static to an Azure Blob container (static / static-staging).
#
# Used by GitHub Actions (deploy-to-webapp.yml) and can be run locally:
#   export AZURE_STORAGE_CONNECTION_STRING="..."
#   ./Backoffice/azure/upload-static-assets.sh
#
# Upload strategy:
#   1. AzCopy dry-run — discover files that differ from blob storage
#   2. AzCopy sync    — upload only those files (azcopy sync has no --cache-control flag)
#   3. az storage blob update — set Cache-Control on newly synced files only
#   4. az storage blob upload-batch — fallback when AzCopy is not installed
#
# Optional env:
#   STATIC_BLOB_CONTAINER            default: static  (use static-staging for staging app)
#   STATIC_SOURCE_DIR                default: Backoffice/app/static
#   STATIC_STORAGE_ACCOUNT_NAME      override AccountName parsed from connection string
#   STATIC_CONFIGURE_CORS=1          one-time blob CORS setup (account-level)
#   STATIC_CORS_ORIGINS              space-separated origins when STATIC_CONFIGURE_CORS=1
#   STATIC_FORCE_UPLOAD=1            skip dry-run short-circuit (full sync + cache-control on changed)
#   STATIC_CHANGED_FILES             newline-separated blob paths (relative to static root);
#                                    used for Cache-Control when set; CI may pass git diff output

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

_blob_relative_path() {
  local abs_path="$1"
  local rel="${abs_path#"${SOURCE_DIR}/"}"
  if [[ "$rel" == "$abs_path" ]]; then
    rel="${abs_path#"${SOURCE_DIR}"}"
    rel="${rel#/}"
  fi
  printf '%s' "$rel"
}

_read_changed_files_env() {
  if [[ -z "${STATIC_CHANGED_FILES:-}" ]]; then
    return 0
  fi
  printf '%s\n' "${STATIC_CHANGED_FILES}" | sed '/^[[:space:]]*$/d'
}

# Write blob-relative paths (one per line) for files AzCopy would copy.
_collect_dry_run_files() {
  local dest="$1"
  local out_file="$2"
  local dry_out log_path

  dry_out="$(mktemp)"
  : > "$out_file"

  echo "Scanning for static files that differ from blob storage (AzCopy dry-run) ..."
  azcopy sync "${SOURCE_DIR}/" "${dest}" \
    --recursive \
    --delete-destination=false \
    --dry-run \
    --log-level=WARNING \
    --output-type=json >"$dry_out" 2>&1 || true

  if command -v jq >/dev/null 2>&1; then
    jq -r '
      select(.MessageType == "Dryrun")
      | .MessageContent
      | fromjson?
      | select(.EntityType == "File" and (.Source // "" | length) > 0)
      | .Source
    ' "$dry_out" 2>/dev/null | while IFS= read -r src_path; do
      [[ -z "$src_path" ]] && continue
      _blob_relative_path "$src_path"
    done | sort -u >>"$out_file" || true
  fi

  if [[ ! -s "$out_file" ]]; then
    log_path="$(grep -Eo 'Log file is located at: [^[:space:]]+' "$dry_out" | tail -1 | sed 's/Log file is located at: //' | tr -d '\r' || true)"
    if [[ -n "$log_path" && -f "$log_path" ]]; then
      grep -iE 'MessageType":"Dryrun|"MessageType":"Dryrun"' "$log_path" 2>/dev/null \
        | sed -n 's/.*"Source":"\([^"]*\)".*/\1/p' \
        | while IFS= read -r src_path; do
            [[ -z "$src_path" ]] && continue
            _blob_relative_path "$src_path"
          done | sort -u >>"$out_file" || true
    fi
  fi

  rm -f "$dry_out"
}

_apply_cache_control_headers() {
  local list_file="$1"
  local parallel count

  if [[ ! -s "$list_file" ]]; then
    echo "No files need Cache-Control metadata updates."
    return 0
  fi

  parallel="${STATIC_CACHE_CONTROL_PARALLEL:-32}"
  count="$(wc -l < "$list_file" | tr -d ' ')"
  echo "Setting Cache-Control on ${count} blob(s) (metadata only, parallel=${parallel}) ..."

  # GNU xargs — available on GitHub Actions ubuntu runners.
  xargs -P "${parallel}" -I {} az storage blob update \
    --container-name "${CONTAINER}" \
    --name "{}" \
    --content-cache-control "${CACHE_CONTROL}" \
    --connection-string "${AZURE_STORAGE_CONNECTION_STRING}" \
    --output none \
    < "$list_file"
}

_upload_with_azcopy() {
  local sas expiry dest files_to_sync cache_control_files
  expiry="$(date -u -d "+2 hours" '+%Y-%m-%dT%H:%MZ' 2>/dev/null || date -u -v+2H '+%Y-%m-%dT%H:%MZ')"
  sas="$(az storage container generate-sas \
    --name "${CONTAINER}" \
    --permissions acwrl \
    --expiry "${expiry}" \
    --connection-string "${AZURE_STORAGE_CONNECTION_STRING}" \
    -o tsv)"
  dest="https://${ACCOUNT_NAME}.blob.core.windows.net/${CONTAINER}?${sas}"

  files_to_sync="$(mktemp)"
  cache_control_files="$(mktemp)"
  trap 'rm -f "$files_to_sync" "$cache_control_files"' RETURN

  if [[ "${STATIC_FORCE_UPLOAD:-}" == "1" ]]; then
    echo "STATIC_FORCE_UPLOAD=1 — skipping dry-run short-circuit."
    find "${SOURCE_DIR}" -type f -printf '%P\n' | sort -u >"$files_to_sync"
  else
    _collect_dry_run_files "${dest}" "$files_to_sync"
  fi

  if [[ ! -s "$files_to_sync" ]]; then
    echo "AzCopy dry-run: no static files differ from blob storage; skipping sync and Cache-Control pass."
    return 0
  fi

  echo "AzCopy dry-run: $(wc -l < "$files_to_sync" | tr -d ' ') file(s) to sync."
  echo "Syncing static assets with AzCopy (parallel; skips unchanged files) ..."
  # Trailing slash on source: sync contents of the directory into the container root.
  # Note: azcopy sync does not support --cache-control; headers are applied after sync via az cli.
  azcopy sync "${SOURCE_DIR}/" "${dest}" \
    --recursive \
    --delete-destination=false \
    --log-level=WARNING \
    --output-type=text

  if [[ -n "${STATIC_CHANGED_FILES:-}" ]]; then
    _read_changed_files_env | sort -u >"$cache_control_files"
  else
    cp "$files_to_sync" "$cache_control_files"
  fi

  _apply_cache_control_headers "$cache_control_files"
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
