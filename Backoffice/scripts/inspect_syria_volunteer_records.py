"""
List FormData records for Syria volunteers (2024) to see which two rows contribute.
Run: cd Backoffice && python scripts/inspect_syria_volunteer_records.py
"""
import logging
import os
import sys

logger = logging.getLogger(__name__)
BACKOFFICE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKOFFICE not in sys.path:
    sys.path.insert(0, BACKOFFICE)
os.chdir(BACKOFFICE)

def run():
    from app import create_app
    from app.extensions import db
    from app.models import FormData, FormItem, IndicatorBank, AssignmentEntityStatus, AssignedForm, Country

    app = create_app()
    with app.app_context():
        # Syria country_id = 167 (from inspect 47087)
        # AssignmentEntityStatus 398 = Syria 2024 Approved
        syria_id = 167
        aes_398 = db.session.get(AssignmentEntityStatus, 398)
        if not aes_398:
            logger.warning("AssignmentEntityStatus 398 not found.")
            return
        # All FormData for this submission (entity_id=167, status Approved, period 2024)
        from sqlalchemy.orm import joinedload
        rows = (
            FormData.query
            .options(joinedload(FormData.form_item))
            .join(FormItem, FormData.form_item_id == FormItem.id)
            .join(IndicatorBank, FormItem.indicator_bank_id == IndicatorBank.id)
            .filter(FormData.assignment_entity_status_id == 398)
            .all()
        )
        logger.info("FormData rows for Syria 2024 submission (assignment_entity_status_id=398):")
        logger.info("  (Volunteer-related form items only if filtered by name match; here we show all for this submission.)")
        # Get all for this AES
        all_fd = FormData.query.filter(FormData.assignment_entity_status_id == 398).all()
        for r in all_fd:
            fi = db.session.get(FormItem, r.form_item_id) if r.form_item_id else None
            ind = db.session.get(IndicatorBank, fi.indicator_bank_id) if fi and fi.indicator_bank_id else None
            val = getattr(r, "value", None) or getattr(r, "total_value", None) or r.get_effective_value()
            logger.info("  FormData id=%s  form_item_id=%s  value=%r  indicator=%s (id=%s)", r.id, r.form_item_id, val, ind.name if ind else 'N/A', ind.id if ind else None)
        logger.info("Done.")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    run()
