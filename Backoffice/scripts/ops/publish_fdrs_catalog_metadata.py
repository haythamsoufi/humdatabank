#!/usr/bin/env python3
"""Publish FDRS catalog metadata that a filename match left blank.

Some Manage Resources rows already hold the production file, but they were
saved with no subcategory or no publication date. ``/api/documents?type=``
then skips them, and the Everyone Counts page cannot build a year. This fills
only the blank fields from the legacy catalog. It does not replace a date or
a subcategory that is already set, and it does not download files.

A catalog row that is not in Databank at all (the FDRS videos playlist) is
created as a publication with its link.

Dry run (default):

    python scripts/ops/publish_fdrs_catalog_metadata.py

Write:

    python scripts/ops/publish_fdrs_catalog_metadata.py --apply
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from datetime import date
from pathlib import Path


def _bootstrap() -> None:
    for candidate in (Path("/app"), Path(__file__).resolve().parent.parent.parent):
        if (candidate / "app").is_dir() and (candidate / "run.py").is_file():
            root = str(candidate)
            if root not in sys.path:
                sys.path.insert(0, root)
            scripts = str(candidate / "scripts")
            if scripts not in sys.path:
                sys.path.insert(0, scripts)
            return
    from _bootstrap import setup_cli_paths

    setup_cli_paths(__file__)


_bootstrap()


def _load_sync_ops():
    path = Path(__file__).resolve().parent / "sync_fdrs_resources.py"
    spec = importlib.util.spec_from_file_location("sync_fdrs_resources_ops", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def publication_date_for_catalog_year(year):
    """1 January of a catalog year. ``0`` is not a date."""
    try:
        number = int(year)
    except (TypeError, ValueError):
        return None
    if number < 1900 or number > 2100:
        return None
    return date(number, 1, 1)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Write the blank metadata.")
    parser.add_argument("--base-url", default="")
    args = parser.parse_args()

    ops = _load_sync_ops()
    key = ops._api_key()
    if not key:
        print("FDRS_DATA_API_KEY is required", file=sys.stderr)
        return 1
    base_url = args.base_url or __import__("os").environ.get("FDRS_DATA_API_BASE") or "https://data-api.ifrc.org"

    from app import create_app
    from app.extensions import db
    from app.models.documents import Resource, ResourceSubcategory, ResourceTranslation

    sync = ops._load_sync()
    payload = sync.fetch_global_catalog(base_url, key)
    app = create_app()
    with app.app_context():
        plan = sync.build_plan(sync.parse_catalog(payload), sync.stored_translations_from_db())
        backup = []
        creates = []

        def subcategory_for(name: str) -> ResourceSubcategory:
            row = ResourceSubcategory.query.filter(
                db.func.lower(ResourceSubcategory.name) == (name or "").casefold()
            ).first()
            if row is not None:
                return row
            row = ResourceSubcategory(name=(name or "Publication")[:120], display_order=100)
            db.session.add(row)
            db.session.flush()
            return row

        for action in plan["sync"]:
            published = publication_date_for_catalog_year(action.get("year"))
            resource = Resource.query.get(action["resource_id"]) if action.get("resource_id") else None
            if resource is None:
                creates.append({
                    "title": action.get("title"),
                    "subcategory": action.get("subcategory"),
                    "publication_date": published.isoformat() if published else None,
                    "files": [
                        {"language": item.get("language"), "name": item.get("name"), "video": bool(item.get("video"))}
                        for item in action.get("files") or []
                    ],
                })
                if not args.apply:
                    continue
                resource = Resource(
                    resource_type="publication",
                    default_title=(action.get("title") or "Untitled")[:255],
                    default_description=action.get("description") or None,
                    publication_date=published,
                    resource_subcategory=subcategory_for(action.get("subcategory") or ""),
                )
                db.session.add(resource)
                db.session.flush()
                for item in action.get("files") or []:
                    language = sync.normalize_language(item.get("language"))
                    translation = ResourceTranslation(
                        resource_id=resource.id,
                        language_code=language,
                        title=(action.get("title") or item.get("name") or "Untitled")[:255],
                        description=action.get("description") or None,
                        filename=None if item.get("video") else (item.get("name") or "")[:255],
                        external_url=(item.get("url") or "")[:1000] if item.get("video") else None,
                    )
                    db.session.add(translation)
                continue

            before = {
                "id": resource.id,
                "title": resource.default_title,
                "resource_type": resource.resource_type,
                "subcategory": resource.resource_subcategory.name if resource.resource_subcategory else None,
                "publication_date": resource.publication_date.isoformat() if resource.publication_date else None,
            }
            after = dict(before)
            if resource.resource_type != "publication":
                after["resource_type"] = "publication"
                if args.apply:
                    resource.resource_type = "publication"
            if resource.resource_subcategory_id is None and action.get("subcategory"):
                after["subcategory"] = action["subcategory"]
                if args.apply:
                    resource.resource_subcategory = subcategory_for(action["subcategory"])
            if resource.publication_date is None and published is not None:
                after["publication_date"] = published.isoformat()
                if args.apply:
                    resource.publication_date = published
            if after != before:
                backup.append({"before": before, "after": after})

        if args.apply:
            db.session.commit()
        else:
            db.session.rollback()

        print(json.dumps({
            "apply": bool(args.apply),
            "updates": backup,
            "creates": creates,
        }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
