#!/usr/bin/env python3
"""Copy sector logo files between Backoffice environments.

On production, export the catalogue::

    python scripts/ops/migrate_sector_logos.py --export

On staging, apply a manifest plus the files saved under the same filenames::

    python scripts/ops/migrate_sector_logos.py --manifest /tmp/sector-logos.json --files /tmp/sector-logos
    python scripts/ops/migrate_sector_logos.py --manifest /tmp/sector-logos.json --files /tmp/sector-logos --apply

Sectors are matched by name. The staging row keeps its id and receives the
production logo filename and file bytes.
"""
from __future__ import annotations

import argparse
import json
import sys
import tarfile
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

from app import create_app  # noqa: E402


def _export(app, output: Path | None, archive: Path | None) -> int:
    from app.models import Sector
    from app.services.platform import storage_service as storage

    rows = []
    files: list[tuple[str, bytes]] = []
    with app.app_context():
        for sector in Sector.query.order_by(Sector.name).all():
            filename = (sector.logo_filename or "").strip()
            data = b""
            exists = False
            if filename and storage.exists(storage.SYSTEM, f"sectors/{filename}"):
                data = storage.download(storage.SYSTEM, f"sectors/{filename}")
                exists = True
                files.append((filename, data))
            rows.append(
                {
                    "name": sector.name,
                    "logo_filename": filename or None,
                    "file_exists": exists,
                    "is_active": bool(sector.is_active),
                }
            )
    text = json.dumps(rows, indent=2)
    if output:
        output.write_text(text, encoding="utf-8")
    if archive:
        archive.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(archive, "w:gz") as bundle:
            manifest = tarfile.TarInfo("sector-logos.json")
            payload = text.encode("utf-8")
            manifest.size = len(payload)
            import io
            bundle.addfile(manifest, io.BytesIO(payload))
            for filename, data in files:
                info = tarfile.TarInfo(f"files/{filename}")
                info.size = len(data)
                bundle.addfile(info, io.BytesIO(data))
    print(json.dumps({
        "exported": len(rows),
        "with_file": len(files),
        "output": str(output) if output else None,
        "archive": str(archive) if archive else None,
    }))
    return 0


def _apply(app, manifest_path: Path, files_dir: Path, apply: bool) -> int:
    from app.extensions import db
    from app.models import Sector
    from app.services.platform import storage_service as storage

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    summary = {"apply": apply, "updated": [], "missing_file": [], "unmatched": []}
    with app.app_context():
        by_name = {(sector.name or "").casefold(): sector for sector in Sector.query.all()}
        for row in manifest:
            name = (row.get("name") or "").strip()
            filename = (row.get("logo_filename") or "").strip()
            if not name or not filename:
                continue
            sector = by_name.get(name.casefold())
            if sector is None:
                summary["unmatched"].append(name)
                continue
            source = files_dir / filename
            if not source.is_file():
                summary["missing_file"].append(filename)
                continue
            data = source.read_bytes()
            summary["updated"].append(
                {
                    "name": sector.name,
                    "id": sector.id,
                    "previous_logo_filename": sector.logo_filename,
                    "logo_filename": filename,
                    "bytes": len(data),
                }
            )
            if not apply:
                continue
            storage.upload(storage.SYSTEM, f"sectors/{filename}", data)
            sector.logo_filename = filename
            storage.publish_system_logo_to_cdn("sectors", filename)
        if apply:
            db.session.commit()
    print(json.dumps(summary, indent=2))
    return 0 if not summary["missing_file"] else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--export", action="store_true")
    parser.add_argument("--output")
    parser.add_argument("--archive")
    parser.add_argument("--manifest")
    parser.add_argument("--files")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    app = create_app()
    from app.services.platform.storage_service import adopt_container_storage_settings
    adopt_container_storage_settings(app)
    if args.export:
        return _export(app, Path(args.output) if args.output else None, Path(args.archive) if args.archive else None)
    manifest = args.manifest
    files = args.files
    if args.archive and not args.export:
        extract_root = Path("/tmp/sector-logos-extracted")
        extract_root.mkdir(parents=True, exist_ok=True)
        with tarfile.open(args.archive, "r:gz") as bundle:
            bundle.extractall(extract_root)
        manifest = str(extract_root / "sector-logos.json")
        files = str(extract_root / "files")
    if not manifest or not files:
        parser.error("--manifest and --files are required unless --export or --archive")
    return _apply(app, Path(manifest), Path(files), args.apply)


if __name__ == "__main__":
    raise SystemExit(main())
