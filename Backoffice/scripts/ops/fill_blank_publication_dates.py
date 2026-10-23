#!/usr/bin/env python3
"""Set a publication date when a resource has none and its name has one year.

The public site uses ``publication_date.year``. A blank date makes it read a
year out of the file name instead. This fills only blank dates, as 1 January
of the single year in the title or file name. ``Strategy 2030`` is not treated
as that year. A name with no year, or with more than one, is left unchanged.

Dry run (default):

    python scripts/ops/fill_blank_publication_dates.py

Write:

    python scripts/ops/fill_blank_publication_dates.py --apply
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

for candidate in (Path("/app"), Path(__file__).resolve().parent.parent.parent):
    if (candidate / "app").is_dir() and (candidate / "run.py").is_file():
        root = str(candidate)
        if root not in sys.path:
            sys.path.insert(0, root)
        break
else:
    from _bootstrap import setup_cli_paths

    setup_cli_paths(__file__)

_YEAR = re.compile(r"(?:19|20)\d{2}")
_STRATEGY_2030 = re.compile(r"strateg\w*\s+2030|estrategia\s+2030", re.IGNORECASE)


def years_in(*texts: str | None) -> list[int]:
    found: set[int] = set()
    for text in texts:
        if not text:
            continue
        for match in _YEAR.finditer(text):
            year = int(match.group(0))
            if year == 2030 and _STRATEGY_2030.search(text):
                continue
            if 1990 <= year <= date.today().year + 1:
                found.add(year)
    return sorted(found)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Write blank publication dates.")
    args = parser.parse_args()

    from app import create_app
    from app.extensions import db
    from app.models.documents import Resource

    app = create_app()
    with app.app_context():
        updates = []
        skipped = []
        for resource in Resource.query.filter(Resource.publication_date.is_(None)).order_by(Resource.id).all():
            texts = [resource.default_title]
            for translation in resource.translations:
                texts.extend([translation.title, translation.filename])
            years = years_in(*texts)
            row = {
                "id": resource.id,
                "title": resource.default_title,
                "type": resource.resource_type,
                "years": years,
            }
            if len(years) != 1:
                skipped.append(row)
                continue
            published = date(years[0], 1, 1)
            updates.append({**row, "publication_date": published.isoformat()})
            if args.apply:
                resource.publication_date = published
        if args.apply:
            db.session.commit()
        else:
            db.session.rollback()
        print(json.dumps({
            "apply": bool(args.apply),
            "updates": updates,
            "skipped": skipped,
        }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
