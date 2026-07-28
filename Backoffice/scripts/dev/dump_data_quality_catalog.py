#!/usr/bin/env python3
"""
Dump FDRS v1 QoD catalog KPI codes mapped to form items for a template (default: 21).

Usage:
    python scripts/dump_data_quality_catalog.py
    python scripts/dump_data_quality_catalog.py --template-id 21
"""
from __future__ import annotations

import argparse
import logging
import os
import sys

script_dir = os.path.dirname(os.path.abspath(__file__))
backoffice_dir = os.path.dirname(script_dir)
if backoffice_dir not in sys.path:
    sys.path.insert(0, backoffice_dir)
if "FLASK_CONFIG" not in os.environ:
    os.environ["FLASK_CONFIG"] = "development"

logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Map QoD catalog KPIs to form items")
    parser.add_argument("--template-id", type=int, default=21)
    args = parser.parse_args()

    from app import create_app
    from sqlalchemy.orm import joinedload

    from app.models.form_items import FormItem
    from app.models.forms import FormTemplate
    from app.services.data_quality.catalogs import fdrs_v1_catalog as cat

    app = create_app()
    with app.app_context():
        template = FormTemplate.query.get(args.template_id)
        if not template:
            logger.error("Template %s not found", args.template_id)
            return 1

        version_id = template.published_version_id
        logger.info("Template %s (%s) published_version_id=%s", template.id, template.name, version_id)

        groups = {
            "governance": cat.GOVERNANCE_KPI_CODES,
            "reach": cat.REACH_KPI_CODES,
            "disaggregation": cat.DISAGG_INDICATOR_KPI_CODES,
            "finance_income": (cat.FINANCE_TOTAL_INCOME,),
            "finance_expenditure": (cat.FINANCE_TOTAL_EXPENDITURE,),
            "income_sources": cat.INCOME_SOURCE_KPI_CODES,
        }

        missing = []
        for group_name, codes in groups.items():
            logger.info("--- %s ---", group_name)
            for code in codes:
                items = (
                    FormItem.query.filter(
                        FormItem.template_id == args.template_id,
                        FormItem.archived == False,
                        FormItem.indicator_bank_id.isnot(None),
                    )
                    .options(joinedload(FormItem.indicator_bank))
                    .all()
                )
                if version_id:
                    items = [i for i in items if i.version_id == version_id or i.version_id is None]
                item = next(
                    (
                        i
                        for i in items
                        if i.indicator_bank and (i.indicator_bank.fdrs_kpi_code or "").strip() == code
                    ),
                    None,
                )
                if item:
                    logger.info("  OK  %s -> item_id=%s label=%r", code, item.id, (item.label or "")[:60])
                else:
                    logger.warning("  MISS %s", code)
                    missing.append(code)

        logger.info("Summary: %d missing of %d catalog codes", len(missing), sum(len(v) for v in groups.values()))
        if missing:
            logger.info("Missing codes: %s", ", ".join(missing))
        return 0 if not missing else 2


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
