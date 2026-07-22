#!/usr/bin/env python3
"""Enable manual row totals on T22 Funding Requirements matrix (item 1303)."""

from __future__ import annotations

import os
import sys

script_dir = os.path.dirname(os.path.abspath(__file__))
backoffice_dir = os.path.dirname(script_dir)
if backoffice_dir not in sys.path:
    sys.path.insert(0, backoffice_dir)

if "FLASK_CONFIG" not in os.environ:
    os.environ["FLASK_CONFIG"] = "development"

ITEM_ID = 1303


def main() -> None:
    from app import create_app
    from app.extensions import db
    from app.models.form_items import FormItem

    app = create_app()
    with app.app_context():
        item = db.session.get(FormItem, ITEM_ID)
        if not item:
            raise SystemExit(f"FormItem {ITEM_ID} not found")

        config = dict(item.config or {})
        mc = dict(config.get("matrix_config") or {})
        mc["show_row_totals"] = True
        mc["row_total_manual_enabled"] = True
        mc["row_total_validation"] = "partial"
        config["matrix_config"] = mc
        item.config = config
        db.session.add(item)
        db.session.commit()
        print(
            f"Patched item {ITEM_ID}: row_total_manual_enabled=True, "
            f"row_total_validation=partial, show_row_totals=True"
        )


if __name__ == "__main__":
    main()
