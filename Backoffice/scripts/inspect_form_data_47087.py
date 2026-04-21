"""
Inspect form_data record 47087 to verify volunteer value and links.
Run: cd Backoffice && python scripts/inspect_form_data_47087.py
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
        fd = db.session.get(FormData, 47087)
        if not fd:
            logger.warning("FormData id 47087 not found.")
            return
        logger.info("FormData id: %s", fd.id)
        logger.info("  form_item_id: %s", fd.form_item_id)
        logger.info("  assignment_entity_status_id: %s", fd.assignment_entity_status_id)
        logger.info("  value: %r", fd.value)
        logger.info("  disagg_data type: %s", type(fd.disagg_data))
        if isinstance(fd.disagg_data, dict):
            logger.info("  disagg_data keys: %s", list(fd.disagg_data.keys()))
            if "values" in fd.disagg_data:
                logger.info("  disagg_data['values']: %s", fd.disagg_data["values"])
        else:
            logger.info("  disagg_data: %s", fd.disagg_data)
        logger.info("  data_not_available: %s", fd.data_not_available)
        logger.info("  not_applicable: %s", fd.not_applicable)
        tv = getattr(fd, "total_value", None)
        logger.info("  total_value (property): %s", tv)
        ev = fd.get_effective_value()
        logger.info("  get_effective_value(): %s", ev)

        fi = db.session.get(FormItem, fd.form_item_id) if fd.form_item_id else None
        if fi:
            logger.info("FormItem id: %s  label: %s", fi.id, getattr(fi, "label", None))
            logger.info("  indicator_bank_id: %s", fi.indicator_bank_id)
            ind = db.session.get(IndicatorBank, fi.indicator_bank_id) if fi.indicator_bank_id else None
            if ind:
                logger.info("  IndicatorBank: %s (id=%s)", ind.name, ind.id)
        aes = db.session.get(AssignmentEntityStatus, fd.assignment_entity_status_id) if fd.assignment_entity_status_id else None
        if aes:
            logger.info("AssignmentEntityStatus id: %s", aes.id)
            logger.info("  entity_id: %s  entity_type: %s", aes.entity_id, aes.entity_type)
            logger.info("  status: %s", aes.status)
            af = db.session.get(AssignedForm, aes.assigned_form_id) if aes.assigned_form_id else None
            if af:
                logger.info("  AssignedForm period_name: %s", af.period_name)
            c = db.session.get(Country, aes.entity_id) if aes.entity_id and aes.entity_type == "country" else None
            if c:
                logger.info("  Country: %s", c.name)
        logger.info("Done.")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    run()
