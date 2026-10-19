#!/usr/bin/env python3
"""Print Manage Resources rows as JSON. Read only."""
from __future__ import annotations

import json
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

from app import create_app
from app.models.documents import Resource, ResourceSubcategory


def main() -> int:
    app = create_app()
    with app.app_context():
        resources = []
        for resource in Resource.query.order_by(Resource.id.asc()).all():
            sub = resource.resource_subcategory.name if resource.resource_subcategory else None
            translations = []
            for translation in resource.translations:
                translations.append({
                    "lang": translation.language_code,
                    "title": translation.title,
                    "filename": translation.filename,
                    "has_file": bool(translation.file_relative_path),
                    "has_thumb": bool(translation.thumbnail_relative_path),
                })
            resources.append({
                "id": resource.id,
                "type": resource.resource_type,
                "title": resource.default_title,
                "date": resource.publication_date.isoformat() if resource.publication_date else None,
                "subcategory": sub,
                "translations": translations,
            })
        subs = [
            {"id": row.id, "name": row.name}
            for row in ResourceSubcategory.query.order_by(ResourceSubcategory.display_order, ResourceSubcategory.id)
        ]
        print(json.dumps({"subcategories": subs, "count": len(resources), "resources": resources}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
