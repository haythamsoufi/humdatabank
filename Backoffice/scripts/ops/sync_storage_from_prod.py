#!/usr/bin/env python3
"""Copy content blobs from production storage into staging.

Restoring the production database into staging copies filenames (sector logos,
publication files, thumbnails, template images) but not the bytes. Those live
in the production uploads container. This copies the missing blobs.

Destination is the storage account of the process you run it in (staging).
Source credentials are explicit so this cannot treat production as the
destination by accident.

From a machine that can reach both accounts:

    $env:SOURCE_AZURE_STORAGE_CONNECTION_STRING = "<prod connection string>"
    $env:SOURCE_AZURE_STORAGE_CONTAINER = "uploads"
    $env:DEST_AZURE_STORAGE_CONNECTION_STRING = "<staging connection string>"
    $env:DEST_AZURE_STORAGE_CONTAINER = "uploads"
    python scripts/ops/sync_storage_from_prod.py
    python scripts/ops/sync_storage_from_prod.py --apply

On the staging App Service container, omit the DEST_* variables. The script
copies the web process storage settings for the destination and still requires
SOURCE_AZURE_STORAGE_CONNECTION_STRING.

Default prefixes: system/ (sector, NS, and SPEF icons, branding), resources/
(publications), admin_documents/, template_assets/. National Society logos
shown on Organization Management are system/ns/{ISO3}.png. Pass --prefix to
replace that list, for example --prefix system/ns/.

The public static container is copied too when both sides name one
(--skip-static to leave it). A full run copies static system/. An explicit
--prefix under system/ (such as system/ns/) copies only that static path,
which is what the organization page loads when the CDN is enabled.

Existing destination blobs are left in place unless --overwrite is set.
Connection strings are never printed.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

for candidate in (Path("/app"), Path(__file__).resolve().parent.parent.parent):
    if (candidate / "app").is_dir() and (candidate / "run.py").is_file():
        root = str(candidate)
        if root not in sys.path:
            sys.path.insert(0, root)
        scripts = str(candidate / "scripts")
        if scripts not in sys.path:
            sys.path.insert(0, scripts)
        break
else:
    from _bootstrap import setup_cli_paths

    setup_cli_paths(__file__)

DEFAULT_PREFIXES = (
    "system/",
    "resources/",
    "admin_documents/",
    "template_assets/",
)
STATIC_PREFIX = "system/"


def static_prefixes_for(prefixes: tuple[str, ...], *, prefixes_were_explicit: bool) -> tuple[str, ...]:
    """Return static-container prefixes that mirror the selected system logos.

    Organization Management loads National Society logos from the public CDN
    at system/ns/ when a CDN is configured, and from the uploads container
    otherwise. An explicit system/ prefix narrows the CDN copy to that path.
    """
    system_prefixes = tuple(p for p in prefixes if p == "system/" or p.startswith("system/"))
    if prefixes_were_explicit and system_prefixes:
        return system_prefixes
    return (STATIC_PREFIX,)


def blobs_to_copy(source_names: set[str], dest_names: set[str], *, overwrite: bool) -> list[str]:
    """Return source blob names that should be written to the destination."""
    if overwrite:
        return sorted(source_names)
    return sorted(name for name in source_names if name not in dest_names)


def _client(connection_string: str, container_name: str):
    from azure.storage.blob import BlobServiceClient

    service = BlobServiceClient.from_connection_string(connection_string)
    return service.get_container_client(container_name)


def _account_marker(connection_string: str, container_name: str) -> str:
    parts = {}
    for piece in connection_string.split(";"):
        if "=" not in piece:
            continue
        key, value = piece.split("=", 1)
        parts[key.strip().lower()] = value.strip()
    account = parts.get("accountname") or parts.get("blobendpoint") or "unknown"
    return f"{account.lower()}::{container_name.strip().lower()}"


def _list_names(container, prefix: str) -> set[str]:
    return {blob.name for blob in container.list_blobs(name_starts_with=prefix)}


def _copy_blob(source_container, dest_container, name: str) -> int:
    from azure.storage.blob import ContentSettings

    source_blob = source_container.get_blob_client(name)
    props = source_blob.get_blob_properties()
    settings = ContentSettings(
        content_type=getattr(props.content_settings, "content_type", None),
        content_disposition=getattr(props.content_settings, "content_disposition", None),
        cache_control=getattr(props.content_settings, "cache_control", None),
    )
    downloader = source_blob.download_blob()
    dest_container.upload_blob(
        name=name,
        data=downloader.chunks(),
        overwrite=True,
        content_settings=settings,
    )
    return int(props.size or 0)


def _sync_container(source, dest, prefixes: tuple[str, ...], *, apply: bool, overwrite: bool, label: str) -> dict:
    planned: list[str] = []
    source_count = 0
    for prefix in prefixes:
        source_names = _list_names(source, prefix)
        dest_names = _list_names(dest, prefix)
        source_count += len(source_names)
        planned.extend(blobs_to_copy(source_names, dest_names, overwrite=overwrite))
    planned = sorted(set(planned))
    copied = 0
    copied_bytes = 0
    errors: list[str] = []
    if apply:
        for name in planned:
            try:
                copied_bytes += _copy_blob(source, dest, name)
                copied += 1
            except Exception as exc:  # noqa: BLE001 — keep going and report the blob
                errors.append(f"{name}: {exc}")
    summary = {
        "container": label,
        "source_blobs": source_count,
        "to_copy": len(planned),
        "copied": copied,
        "copied_bytes": copied_bytes,
        "errors": errors,
        "sample": planned[:20],
    }
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="Copy missing blobs. Default is a dry run.")
    parser.add_argument("--overwrite", action="store_true", help="Replace blobs that already exist on the destination.")
    parser.add_argument(
        "--prefix",
        action="append",
        default=None,
        help="Blob prefix to copy (repeatable). Replaces the default content prefixes.",
    )
    parser.add_argument("--skip-static", action="store_true", help="Do not copy the public static container.")
    args = parser.parse_args()

    source_cs = (os.environ.get("SOURCE_AZURE_STORAGE_CONNECTION_STRING") or "").strip()
    if not source_cs:
        print("SOURCE_AZURE_STORAGE_CONNECTION_STRING is required", file=sys.stderr)
        return 1
    source_container_name = (os.environ.get("SOURCE_AZURE_STORAGE_CONTAINER") or "uploads").strip()

    dest_cs = (os.environ.get("DEST_AZURE_STORAGE_CONNECTION_STRING") or "").strip()
    dest_container_name = (os.environ.get("DEST_AZURE_STORAGE_CONTAINER") or "").strip()
    dest_static_name = (os.environ.get("DEST_STATIC_BLOB_CONTAINER") or "").strip()
    if not dest_cs:
        from app import create_app
        from app.services.platform.storage_service import adopt_container_storage_settings

        app = create_app()
        with app.app_context():
            adopt_container_storage_settings(app)
            dest_cs = (app.config.get("AZURE_STORAGE_CONNECTION_STRING") or "").strip()
            dest_container_name = dest_container_name or (app.config.get("AZURE_STORAGE_CONTAINER") or "uploads").strip()
            dest_static_name = dest_static_name or (app.config.get("STATIC_BLOB_CONTAINER") or "").strip()
    dest_container_name = dest_container_name or "uploads"

    if _account_marker(source_cs, source_container_name) == _account_marker(dest_cs, dest_container_name):
        print("Refusing to copy: source and destination are the same storage account and container.", file=sys.stderr)
        return 1

    prefixes = tuple(args.prefix) if args.prefix else DEFAULT_PREFIXES
    source = _client(source_cs, source_container_name)
    dest = _client(dest_cs, dest_container_name)
    uploads = _sync_container(source, dest, prefixes, apply=args.apply, overwrite=args.overwrite, label=dest_container_name)

    static_summary = None
    static_skipped = None
    source_static_name = (os.environ.get("SOURCE_STATIC_BLOB_CONTAINER") or "").strip()
    static_prefixes = static_prefixes_for(prefixes, prefixes_were_explicit=bool(args.prefix))
    if args.skip_static:
        static_skipped = "skip-static"
    elif not static_prefixes:
        static_skipped = "no system prefix"
    elif not source_static_name or not dest_static_name:
        static_skipped = "missing static container name"
    elif _account_marker(source_cs, source_static_name) == _account_marker(dest_cs, dest_static_name):
        static_skipped = "same account and container"
    else:
        static_summary = _sync_container(
            _client(source_cs, source_static_name),
            _client(dest_cs, dest_static_name),
            static_prefixes,
            apply=args.apply,
            overwrite=args.overwrite,
            label=dest_static_name,
        )

    import json
    print(json.dumps({
        "apply": bool(args.apply),
        "prefixes": list(prefixes),
        "static_prefixes": list(static_prefixes) if not args.skip_static else [],
        "uploads": uploads,
        "static": static_summary,
        "static_skipped": static_skipped,
    }, indent=2))
    if uploads["errors"] or (static_summary and static_summary["errors"]):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
