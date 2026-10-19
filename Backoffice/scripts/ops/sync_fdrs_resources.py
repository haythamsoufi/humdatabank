#!/usr/bin/env python3
"""Sync global FDRS resources from data.ifrc.org into Manage Resources.

The source is the legacy catalog:

    GET https://data-api.ifrc.org/api/documents?isglobal=true

That list is Everyone Counts, analysis notes, user guides, and videos.
Every FDRS resource is checked. A file or cover already stored is kept only
when the blob is in storage; a missing blob is downloaded or rendered again.
Resources that exist only in Databank (extra languages, local guidance) are
not deleted.

Dry run (default) prints the comparison and writes nothing:

    python scripts/ops/sync_fdrs_resources.py

Write on the machine whose database and storage you mean to update
(local, or the staging/production container after the external_url migration):

    python scripts/ops/sync_fdrs_resources.py --apply

The API key is FDRS_DATA_API_KEY from the environment or Backoffice/.env.
It is never printed.
"""
from __future__ import annotations

import argparse
import json
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


def _container_env_value(name: str) -> str:
    """Read one variable from the web process. The value is not logged."""
    if not os.path.isdir("/proc"):
        return ""
    paths = ["/proc/1/environ"]
    try:
        entries = os.listdir("/proc")
    except OSError:
        entries = []
    for entry in entries:
        if not entry.isdigit():
            continue
        cmdline_path = f"/proc/{entry}/cmdline"
        try:
            with open(cmdline_path, "rb") as handle:
                cmdline = handle.read().replace(b"\0", b" ").decode("utf-8", "replace")
        except OSError:
            continue
        if "gunicorn" in cmdline and "run:app" in cmdline:
            paths.append(f"/proc/{entry}/environ")
    needle = name.encode("utf-8") + b"="
    for path in paths:
        try:
            with open(path, "rb") as handle:
                raw = handle.read()
        except OSError:
            continue
        for item in raw.split(b"\0"):
            if not item.startswith(needle):
                continue
            try:
                return item.split(b"=", 1)[1].decode("utf-8").strip()
            except UnicodeDecodeError:
                return ""
    return ""


def _api_key() -> str:
    key = (os.environ.get("FDRS_DATA_API_KEY") or "").strip()
    if key:
        return key
    key = _container_env_value("FDRS_DATA_API_KEY")
    if key:
        return key
    env_path = Path(root) / ".env" if "root" in globals() else None
    if env_path is None:
        env_path = Path(__file__).resolve().parents[2] / ".env"
    if env_path.is_file():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("FDRS_DATA_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


_STORAGE_ENV_KEYS = (
    "AZURE_STORAGE_CONNECTION_STRING",
    "AZURE_STORAGE_CONTAINER",
    "UPLOAD_STORAGE_PROVIDER",
    "UPLOAD_FOLDER",
    "STATIC_CDN_URL",
    "STATIC_BLOB_CONTAINER",
)


def _adopt_storage_env() -> bool:
    """Copy blob settings from the web process before the app config is imported."""
    if (os.environ.get("AZURE_STORAGE_CONNECTION_STRING") or "").strip():
        return True
    if not os.path.isdir("/proc"):
        return False
    paths = ["/proc/1/environ"]
    try:
        entries = os.listdir("/proc")
    except OSError:
        entries = []
    for entry in entries:
        if not entry.isdigit():
            continue
        try:
            with open(f"/proc/{entry}/cmdline", "rb") as handle:
                cmdline = handle.read().replace(b"\0", b" ").decode("utf-8", "replace")
        except OSError:
            continue
        if "gunicorn" in cmdline and "run:app" in cmdline:
            paths.append(f"/proc/{entry}/environ")
            break
    found = {}
    for path in paths:
        try:
            with open(path, "rb") as handle:
                raw = handle.read()
        except OSError:
            continue
        for item in raw.split(b"\0"):
            if b"=" not in item:
                continue
            key, value = item.split(b"=", 1)
            try:
                name = key.decode("utf-8")
                text = value.decode("utf-8").strip()
            except UnicodeDecodeError:
                continue
            if name in _STORAGE_ENV_KEYS and text and name not in found:
                found[name] = text
        if found.get("AZURE_STORAGE_CONNECTION_STRING"):
            break
    connection = found.get("AZURE_STORAGE_CONNECTION_STRING")
    if not connection:
        return False
    os.environ["AZURE_STORAGE_CONNECTION_STRING"] = connection
    os.environ["UPLOAD_STORAGE_PROVIDER"] = found.get("UPLOAD_STORAGE_PROVIDER") or "azure_blob"
    for name in ("AZURE_STORAGE_CONTAINER", "UPLOAD_FOLDER", "STATIC_CDN_URL", "STATIC_BLOB_CONTAINER"):
        if found.get(name):
            os.environ[name] = found[name]
    return True


def _load_sync():
    try:
        from plugins.fdrs.services import fdrs_resource_sync as module
        if hasattr(module, "apply_plan"):
            return module
    except ImportError:
        pass
    path = os.environ.get("FDRS_RESOURCE_SYNC_PATH", "/tmp/fdrs_resource_sync.py")
    import importlib.util
    spec = importlib.util.spec_from_file_location("fdrs_resource_sync_upload", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load resource sync from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="Create missing resources and download files.")
    parser.add_argument("--detach", action="store_true", help="Run --apply in the background and return.")
    parser.add_argument("--base-url", default=os.environ.get("FDRS_DATA_API_BASE") or "https://data-api.ifrc.org")
    args = parser.parse_args()

    if args.detach:
        import shutil
        import subprocess
        if os.environ.get("FDRS_RESOURCE_SYNC_FOREGROUND") == "1":
            args.detach = False
        else:
            copy_path = "/tmp/sync_fdrs_resources.py"
            shutil.copy(os.path.abspath(__file__), copy_path)
            log = open("/tmp/fdrs_resource_sync.log", "w", encoding="utf-8")
            child_env = dict(os.environ)
            child_env["FDRS_RESOURCE_SYNC_FOREGROUND"] = "1"
            proc = subprocess.Popen(
                [sys.executable, copy_path, "--apply"],
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                env=child_env,
            )
            print(json.dumps({"detached": True, "pid": proc.pid, "log": "/tmp/fdrs_resource_sync.log"}))
            return 0

    key = _api_key()
    if not key:
        print("FDRS_DATA_API_KEY is required", file=sys.stderr)
        return 1

    storage_ready = _adopt_storage_env()
    if args.apply and os.path.isdir("/proc") and not storage_ready:
        print("Refusing to write: blob storage settings were not found on the web process.", file=sys.stderr)
        return 1

    from app import create_app

    sync = _load_sync()
    payload = sync.fetch_global_catalog(args.base_url, key)
    app = create_app()
    with app.app_context():
        provider = app.config.get("UPLOAD_STORAGE_PROVIDER")
        print(f"storage_provider {provider}", flush=True)
        if args.apply and os.path.isdir("/proc") and provider != "azure_blob":
            print("Refusing to write: storage provider is not azure_blob.", file=sys.stderr)
            return 1
        if args.apply:
            try:
                sync.ensure_external_url_column()
            except Exception as exc:
                print(f"external_url column: {exc}", file=sys.stderr)
                return 1
        plan = sync.build_plan(sync.parse_catalog(payload), sync.stored_translations_from_db())
        result = None
        if args.apply:
            result = sync.apply_plan(plan)
        summary = {
            "apply": bool(args.apply),
            "storage_provider": app.config.get("UPLOAD_STORAGE_PROVIDER"),
            "fdrs_rows": plan["fdrs_rows"],
            "deduped": plan["deduped"],
            "duplicates_skipped": plan["duplicates_skipped"],
            "in_databank": plan["in_databank"],
            "missing": plan["missing"],
            "create_resources": plan["create_resources"],
            "attach_to_existing": plan["attach_to_existing"],
            "verify_resources": plan.get("verify_resources"),
            "only_databank": plan["only_databank"],
            "files": plan["files"],
            "only_databank_files": plan["only_databank_files"],
            "skipped_duplicates": plan["skipped_duplicates"],
            "result": result,
        }
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        if result and result["errors"]:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
