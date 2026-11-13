#!/usr/bin/env python3
"""Set the text category "Bundle" on National Societies (used by UPR bundle visuals).

Each ISO3 below is mapped to one bundle name. The value is stored in
``national_societies.category_text["Bundle"]`` for the country's active
National Society, and "Bundle" is registered as a text category.

Existing values are left alone unless --overwrite is given. Prints a JSON
backup of anything it would replace.

Dry run (default):

    python scripts/ops/seed_ns_bundles.py

Write:

    python scripts/ops/seed_ns_bundles.py --apply [--overwrite]
"""
from __future__ import annotations

import argparse
import json
import sys
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

CARIB_EN = "English and Dutch-speaking Caribbean"
CARIB_LAT = "Latin Caribbean"
PACIFIC = "Pacific Islands"
MEKONG = "Mekong countries"
MAURITIUS = "Mauritius and Seychelles"
BELARUS_RU = "Belarus and Russia"

BUNDLES: dict[str, str] = {
    "ATG": CARIB_EN,
    "BHS": CARIB_EN,
    "BRB": CARIB_EN,
    "BLR": BELARUS_RU,
    "BLZ": CARIB_EN,
    "KHM": MEKONG,
    "COK": PACIFIC,
    "CUB": CARIB_LAT,
    "DMA": CARIB_EN,
    "DOM": CARIB_LAT,
    "FJI": PACIFIC,
    "GRD": CARIB_EN,
    "GUY": CARIB_EN,
    "JAM": CARIB_EN,
    "KIR": PACIFIC,
    "LAO": MEKONG,
    "MHL": PACIFIC,
    "MUS": MAURITIUS,
    "FSM": PACIFIC,
    "PLW": PACIFIC,
    "RUS": BELARUS_RU,
    "KNA": CARIB_EN,
    "LCA": CARIB_EN,
    "VCT": CARIB_EN,
    "WSM": PACIFIC,
    "SYC": MAURITIUS,
    "SLB": PACIFIC,
    "SUR": CARIB_EN,
    "THA": MEKONG,
    "TON": PACIFIC,
    "TTO": CARIB_EN,
    "TUV": PACIFIC,
    "VUT": PACIFIC,
    "VNM": MEKONG,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Write the changes.")
    parser.add_argument("--overwrite", action="store_true", help="Replace an existing different Bundle value.")
    args = parser.parse_args()

    from sqlalchemy.orm.attributes import flag_modified

    from app import create_app
    from app.extensions import db
    from app.models import Country, NationalSociety
    from app.utils.organization.country_utils import (
        PART_OF_CATEGORY_TEXT,
        load_part_of_category_catalog,
        remember_part_of_category,
        update_part_of_category_type,
    )

    app = create_app()
    with app.app_context():
        from plugins.upr.dashboards.bundle import bundle_category_name

        category = bundle_category_name()
        catalog = load_part_of_category_catalog()
        print(f"Category '{category}' in catalog as: {catalog.get(category, 'not present')}")

        stats = {"set": 0, "unchanged": 0, "kept_existing": 0, "no_country": [], "no_society": []}
        backup: list[dict] = []
        for iso3, bundle in BUNDLES.items():
            country = Country.query.filter(Country.iso3 == iso3).first()
            if country is None:
                stats["no_country"].append(iso3)
                continue
            society = (
                NationalSociety.query.filter(NationalSociety.country_id == country.id)
                .order_by(NationalSociety.is_active.desc(), NationalSociety.display_order.asc(), NationalSociety.id.asc())
                .first()
            )
            if society is None:
                stats["no_society"].append(iso3)
                continue
            texts = dict(society.category_text) if isinstance(society.category_text, dict) else {}
            current = str(texts.get(category) or "").strip()
            if current == bundle:
                stats["unchanged"] += 1
                continue
            if current and not args.overwrite:
                stats["kept_existing"] += 1
                print(f"KEEP {iso3}: existing '{current}' (wanted '{bundle}')")
                continue
            if current:
                backup.append({"iso3": iso3, "society_id": society.id, "previous": current})
            stats["set"] += 1
            print(f"SET  {iso3} ({society.name}) -> {bundle}")
            if args.apply:
                texts[category] = bundle
                society.category_text = texts
                flag_modified(society, "category_text")

        if backup:
            print("BACKUP " + json.dumps(backup))
        if args.apply:
            if catalog.get(category) is None:
                remember_part_of_category(category, PART_OF_CATEGORY_TEXT)
            elif catalog.get(category) != PART_OF_CATEGORY_TEXT:
                update_part_of_category_type(category, PART_OF_CATEGORY_TEXT)
            db.session.commit()

        print(
            f"{'Applied' if args.apply else 'Dry run'}: set={stats['set']} unchanged={stats['unchanged']} "
            f"kept_existing={stats['kept_existing']} no_country={stats['no_country']} no_society={stats['no_society']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
