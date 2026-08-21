#!/usr/bin/env bash
# Upload Backoffice/app/static to an Azure Blob container (static / static-staging).
#
# Used by GitHub Actions (deploy-to-webapp.yml) and can be run locally:
#   export AZURE_STORAGE_CONNECTION_STRING="..."
#   ./Backoffice/azure/upload-static-assets.sh
#
# Upload strategy:
#   1. AzCopy dry-run — discover files that differ from blob storage
#   2. Incremental: AzCopy sync, then az storage blob update (Cache-Control only)
#   3. FORCE_STATIC_UPLOAD=1: AzCopy copy with --cache-control (set-properties
#      cannot set this HTTP header — only tier/metadata/tags)
#   4. az storage blob upload-batch — fallback when AzCopy is not installed
#
# Optional env:
#   STATIC_BLOB_CONTAINER            default: static  (use static-staging for staging app)
#   STATIC_SOURCE_DIR                default: Backoffice/app/static
#   STATIC_STORAGE_ACCOUNT_NAME      override AccountName parsed from connection string
#   STATIC_CONFIGURE_CORS=1          one-time blob CORS setup (account-level)
#   STATIC_CORS_ORIGINS              space-separated origins when STATIC_CONFIGURE_CORS=1
#   STATIC_FORCE_UPLOAD=1            full AzCopy copy with Cache-Control (skip dry-run)

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
  # Trailing newline is required: callers invoke this once per file inside a
  # `while read` loop piped to `sort -u`. Without it, every path printed in the
  # same loop run concatenates onto one line (no separator), so downstream
  # consumers (see _apply_cache_control_headers) see a single bogus "path" and
  # skip Cache-Control for the entire batch.
  printf '%s\n' "$rel"
}

# Extract blob-relative path from an AzCopy dry-run Source/Destination value.
_dry_run_blob_path() {
  local value="$1"
  if [[ -z "$value" ]]; then
    return 0
  fi
  if [[ "$value" == http://* || "$value" == https://* ]]; then
    # https://account.blob.core.windows.net/container/js/foo.js?... -> js/foo.js
    value="${value#*://${ACCOUNT_NAME}.blob.core.windows.net/${CONTAINER}/}"
    value="${value%%\?*}"
    # See newline comment in _blob_relative_path above — same reasoning applies here.
    printf '%s\n' "$value"
    return 0
  fi
  _blob_relative_path "$value"
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
      | select(.EntityType == "File")
      | if (.Source // "" | test("^https?://")) then .Destination // .Source else .Source end
    ' "$dry_out" 2>/dev/null | while IFS= read -r raw_path; do
      [[ -z "$raw_path" ]] && continue
      _dry_run_blob_path "$raw_path"
    done | sed '/^[[:space:]]*$/d' | sort -u >>"$out_file" || true
  fi

  if [[ ! -s "$out_file" ]]; then
    log_path="$(grep -Eo 'Log file is located at: [^[:space:]]+' "$dry_out" | tail -1 | sed 's/Log file is located at: //' | tr -d '\r' || true)"
    if [[ -n "$log_path" && -f "$log_path" ]]; then
      grep -iE 'MessageType":"Dryrun|"MessageType":"Dryrun"' "$log_path" 2>/dev/null \
        | sed -n 's/.*"Source":"\([^"]*\)".*/\1/p' \
        | while IFS= read -r raw_path; do
            [[ -z "$raw_path" ]] && continue
            _dry_run_blob_path "$raw_path"
          done | sed '/^[[:space:]]*$/d' | sort -u >>"$out_file" || true
    fi
  fi

  rm -f "$dry_out"
}

# Metadata-only Cache-Control via Azure CLI. AzCopy set-properties has no
# --cache-control flag (only tier / metadata / tags), so do not call it here.
# Used after incremental sync (typically a handful of files). Force uploads
# set the header during azcopy copy instead — 500+ az CLI process starts
# would be slower than re-copying ~30MB with the header already set.
_apply_cache_control_headers() {
  local list_file="$1"
  local parallel count xargs_status

  if [[ ! -s "$list_file" ]]; then
    echo "No files need Cache-Control metadata updates."
    return 0
  fi

  count="$(grep -cve '^[[:space:]]*$' "$list_file" || true)"
  parallel="${STATIC_CACHE_CONTROL_PARALLEL:-32}"
  echo "Setting Cache-Control metadata on ${count} synced blob(s) (parallel=${parallel}) ..."

  export CONTAINER SOURCE_DIR CACHE_CONTROL AZURE_STORAGE_CONNECTION_STRING

  set +e
  tr -d '\r' < "$list_file" \
    | sed '/^[[:space:]]*$/d' \
    | xargs -P "${parallel}" -I {} bash -c '
        rel="$1"
        local_file="${SOURCE_DIR}/${rel}"
        if [[ ! -f "${local_file}" ]]; then
          echo "WARN: skipping Cache-Control for missing local file: ${rel}" >&2
          exit 0
        fi
        if ! az storage blob update \
          --container-name "${CONTAINER}" \
          --name "${rel}" \
          --content-cache-control "${CACHE_CONTROL}" \
          --connection-string "${AZURE_STORAGE_CONNECTION_STRING}" \
          --only-show-errors \
          --output none; then
          echo "ERROR: Cache-Control update failed for: ${rel}" >&2
          exit 1
        fi
      ' _ {}
  xargs_status=$?
  set -e

  if [[ "${xargs_status}" -ne 0 ]]; then
    echo "ERROR: Cache-Control pass failed (xargs exit ${xargs_status})." >&2
    return 1
  fi
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
    # copy (not sync) so --cache-control is applied during upload. Quoted
    # "${SOURCE_DIR}/*" is passed to AzCopy (not expanded by bash) so files
    # land at the container root, same as azcopy sync with a trailing slash.
    echo "STATIC_FORCE_UPLOAD=1 — AzCopy copy with Cache-Control (no set-properties)."
    azcopy copy "${SOURCE_DIR}/*" "${dest}" \
      --recursive \
      --overwrite=true \
      --cache-control="${CACHE_CONTROL}" \
      --log-level=WARNING \
      --output-type=text
    return 0
  fi

  _collect_dry_run_files "${dest}" "$files_to_sync"

  if [[ ! -s "$files_to_sync" ]]; then
    echo "AzCopy dry-run: no static files differ from blob storage; skipping sync and Cache-Control pass."
    return 0
  fi

  echo "AzCopy dry-run: $(wc -l < "$files_to_sync" | tr -d ' ') file(s) to sync."
  echo "Syncing static assets with AzCopy (parallel; skips unchanged files) ..."
  # Trailing slash on source: sync contents of the directory into the container root.
  # azcopy sync cannot set Cache-Control; apply it after via az storage blob update.
  azcopy sync "${SOURCE_DIR}/" "${dest}" \
    --recursive \
    --delete-destination=false \
    --log-level=WARNING \
    --output-type=text

  tr -d '\r' < "$files_to_sync" | sed '/^[[:space:]]*$/d' | sort -u >"$cache_control_files"
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
