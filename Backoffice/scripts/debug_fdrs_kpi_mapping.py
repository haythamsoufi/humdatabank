#!/usr/bin/env python3
"""
One-off debug: check why a BaseKPI (e.g. KPI_ReachWASH) might show no_form_item or not import.
Prints: indicator_bank row, form_item row(s) for template 21, and version status (import only uses published).
"""
import logging
import os
import sys

logger = logging.getLogger(__name__)

script_dir = os.path.dirname(os.path.abspath(__file__))
backoffice_dir = os.path.dirname(script_dir)
if backoffice_dir not in sys.path:
    sys.path.insert(0, backoffice_dir)
if "FLASK_CONFIG" not in os.environ:
    os.environ["FLASK_CONFIG"] = "development"

def main():
    base_kpi = (sys.argv[1] if len(sys.argv) > 1 else "KPI_ReachWASH").strip()
    from app import create_app
    from app.models.indicator_bank import IndicatorBank
    from app.models.form_items import FormItem
    from app.models.forms import FormTemplateVersion
    from app.extensions import db

    app = create_app()
    with app.app_context():
        ind = IndicatorBank.query.filter(IndicatorBank.fdrs_kpi_code == base_kpi).first()
        if not ind:
            logger.info("[DEBUG] No indicator_bank with fdrs_kpi_code = %r", base_kpi)
            like = IndicatorBank.query.filter(IndicatorBank.fdrs_kpi_code.like(f"%{base_kpi}%")).all()
            if like:
                logger.info("  Similar: %s", [(i.id, i.fdrs_kpi_code) for i in like])
            return
        logger.info("[DEBUG] Indicator: id=%s, fdrs_kpi_code=%r, name=%r", ind.id, ind.fdrs_kpi_code, getattr(ind, 'name', '')[:60])
        items = FormItem.query.filter(FormItem.indicator_bank_id == ind.id).all()
        logger.info("[DEBUG] FormItem(s) with indicator_bank_id=%s: %d", ind.id, len(items))
        items_21 = [i for i in items if i.template_id == 21]
        has_published = False
        for fi in items:
            version = db.session.get(FormTemplateVersion, fi.version_id) if fi.version_id else None
            status = (version.status or "?").lower() if version else "?"
            logger.info("  item_id=%s, template_id=%s, version_id=%s, version.status=%s", fi.id, fi.template_id, fi.version_id, status)
            if fi.template_id == 21 and status == "published":
                has_published = True
        if not items_21:
            logger.info("  -> No form item for template_id=21 (hence no_form_item_for_template in import).")
        elif not has_published:
            logger.info("  -> Form item exists for template 21 but version is not 'published' (import only uses published).")
        else:
            logger.info("  -> Link OK: indicator + published form item for template 21.")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    main()
