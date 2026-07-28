#!/usr/bin/env python
"""Report per-template scale metrics for version deploy migration planning.

Run from Backoffice/:
    python scripts/template_version_scale_inventory.py

Use output to validate backfill coverage expectations and tune
DEPLOY_MIGRATION_PREFLIGHT_ROW_THRESHOLD in config.
"""
from __future__ import annotations

from sqlalchemy import text

from app import create_app
from app.extensions import db


INVENTORY_SQL = text("""
SELECT
    ft.id AS template_id,
    COALESCE(ftv_pub.name, '(unnamed)') AS template_name,
    COUNT(DISTINCT ftv.id) AS version_count,
    COUNT(DISTINCT fi.id) AS item_count,
    COUNT(DISTINCT CASE WHEN fi.indicator_bank_id IS NOT NULL THEN fi.id END) AS indicator_item_count,
    COUNT(DISTINCT CASE WHEN fi.indicator_bank_id IS NULL THEN fi.id END) AS non_indicator_item_count,
    COUNT(DISTINCT fd.id) AS form_data_rows,
    BOOL_AND(ftv.based_on_version_id IS NULL) AS all_versions_no_lineage
FROM form_template ft
LEFT JOIN form_template_version ftv ON ftv.template_id = ft.id
LEFT JOIN form_template_version ftv_pub ON ftv_pub.id = ft.published_version_id
LEFT JOIN form_item fi ON fi.template_id = ft.id
LEFT JOIN form_data fd ON fd.form_item_id = fi.id
GROUP BY ft.id, ftv_pub.name
ORDER BY form_data_rows DESC NULLS LAST, ft.id
""")


def main() -> int:
    app = create_app()
    with app.app_context():
        rows = db.session.execute(INVENTORY_SQL).mappings().all()
        if not rows:
            print("No templates found.")
            return 0

        print(
            "template_id\ttemplate_name\tversions\titems\tindicators\tnon_indicators\t"
            "form_data_rows\tall_versions_no_lineage"
        )
        total_form_data = 0
        for row in rows:
            fd = int(row['form_data_rows'] or 0)
            total_form_data += fd
            print(
                f"{row['template_id']}\t{row['template_name']}\t"
                f"{row['version_count']}\t{row['item_count']}\t"
                f"{row['indicator_item_count']}\t{row['non_indicator_item_count']}\t"
                f"{fd}\t{row['all_versions_no_lineage']}"
            )
        print(f"\nTotal form_data rows across templates: {total_form_data}")
        print(
            "Suggested DEPLOY_MIGRATION_PREFLIGHT_ROW_THRESHOLD: "
            f"{app.config.get('DEPLOY_MIGRATION_PREFLIGHT_ROW_THRESHOLD', 500000)}"
        )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
