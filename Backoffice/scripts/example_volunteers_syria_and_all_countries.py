"""
Example: how "volunteers in all countries" gets its values (Syria example + bulk).

Data source: Values are stored in the form_data table (FormData.value, FormData.disagg_data),
linked to assignment_entity_status (country + assignment + period) and to form items;
form items link to indicator_bank (metadata only). The tools read from form_data, not
from the indicator bank.

Run from Backoffice (with request context so RBAC grants assigned-data access):
  cd Backoffice && python scripts/example_volunteers_syria_and_all_countries.py

Logic:
- get_value_breakdown / get_indicator_values_for_all_countries:
  Query FormData + AssignmentEntityStatus + FormItem + IndicatorBank. "Volunteers" is
  a POINT indicator: we use the LATEST submission value per country (by period_name year,
  then timestamp), not a sum over periods.
- UPR tools: One value per country from document chunk metadata (UPR KPI block).
"""

import logging
import os
import sys

logger = logging.getLogger(__name__)

# Ensure Backoffice is on path and we load with app context
BACKOFFICE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKOFFICE not in sys.path:
    sys.path.insert(0, BACKOFFICE)
os.chdir(BACKOFFICE)


def run():
    from app import create_app
    from app.services.data_retrieval_service import (
        get_value_breakdown,
        resolve_country,
        get_indicator_values_for_all_countries,
    )
    from app.services.upr.data_retrieval import (
        get_upr_kpi_value,
        get_upr_kpi_values_for_all_countries,
    )

    app = create_app()
    with app.app_context():
        # Request context so RBAC grants assigned-data access (form_data via AssignmentEntityStatus).
        # Without it, check_country_access is False and we only see public form items.
        with app.test_request_context():
            try:
                from app.models import User
                from flask_login import login_user
                user = None
                try:
                    from app.services.authorization_service import AuthorizationService
                    for u in User.query.all():
                        if AuthorizationService.is_system_manager(u):
                            user = u
                            break
                    if not user:
                        user = User.query.first()
                except Exception as e:
                    logger.debug("AuthorizationService/system manager lookup failed: %s", e)
                    user = User.query.first()
                if user:
                    login_user(user)
                    logger.info("Running as user (for RBAC): %s", getattr(user, "email", None) or user.id)
                else:
                    logger.info("Note: no user in DB; only public form data will be visible.")
            except Exception as e:
                logger.info("Note: RBAC setup failed: %s", e)

            logger.info("\n" + "=" * 60)
            logger.info("1) Syria: form_data (get_value_breakdown) – 'Volunteers'")
            logger.info("   Data from form_data table; LATEST submission per country (point indicator).")
            logger.info("=" * 60)
            country = resolve_country("Syria")
            if not country:
                logger.info("   Syria not found in DB (no Country record). Skip.")
            else:
                breakdown = get_value_breakdown(int(country.id), "Volunteers", period=None)
                if "error" in breakdown:
                    logger.info("   Error: %s %s", breakdown.get("error"), breakdown.get("hint", ""))
                else:
                    total = breakdown.get("total")
                    period_used = breakdown.get("period_used")
                    assignment_name = breakdown.get("assignment_name")
                    data_status = breakdown.get("data_status", "")
                    logger.info("   Total (latest): %s", total)
                    logger.info("   Period used: %s", period_used)
                    logger.info("   Assignment: %s", assignment_name)
                    logger.info("   Data status: %s", data_status)
                    logger.info("   Records (chosen submission): %s", breakdown.get("records_count"))

            logger.info("\n" + "=" * 60)
            logger.info("2) Syria: UPR KPI (get_upr_kpi_value) – volunteers from documents")
            logger.info("=" * 60)
            upr = get_upr_kpi_value(country_identifier="Syria", metric="volunteers")
            if upr.get("error"):
                logger.info("   Error: %s", upr.get("error"))
            else:
                logger.info("   Value: %s", upr.get("value"))
                logger.info("   Source: %s page %s", upr.get("source", {}).get("document_title"), upr.get("source", {}).get("page_number"))

            logger.info("\n" + "=" * 60)
            logger.info("3) All countries: form_data (get_indicator_values_for_all_countries)")
            logger.info("   One row per country = LATEST value from form_data (point indicator logic).")
            logger.info("=" * 60)
            all_ind = get_indicator_values_for_all_countries("Volunteers", period=None)
            if not all_ind.get("success"):
                logger.info("   Error: %s", all_ind.get("error"))
            else:
                rows = all_ind.get("rows") or []
                logger.info("   Count: %s countries with data", all_ind.get("count"))
                for r in rows[:8]:
                    logger.info("   %s : %s  period: %s  assignment: %s", r.get("country_name"), r.get("value"), r.get("period_used"), r.get("assignment_name"))
                if len(rows) > 8:
                    logger.info("   ... and %d more", len(rows) - 8)
                syria_row = next((r for r in rows if (r.get("country_name") or "").lower() == "syria"), None)
                if syria_row:
                    logger.info("   [Syria row] %s", syria_row)

            logger.info("\n" + "=" * 60)
            logger.info("4) All countries: UPR KPI (get_upr_kpi_values_for_all_countries)")
            logger.info("=" * 60)
            all_upr = get_upr_kpi_values_for_all_countries("volunteers")
            if not all_upr.get("success"):
                logger.info("   Error: %s", all_upr.get("error"))
            else:
                rows = all_upr.get("rows") or []
                logger.info("   Count: %s countries with UPR data", all_upr.get("count"))
                for r in rows[:8]:
                    logger.info("   %s : %s  source: %s", r.get("country_name"), r.get("value"), (r.get("source") or {}).get("document_title"))
                if len(rows) > 8:
                    logger.info("   ... and %d more", len(rows) - 8)
                syria_upr = next((r for r in rows if (r.get("country_name") or "").lower() == "syria"), None)
                if syria_upr:
                    logger.info("   [Syria row] %s", syria_upr)

            logger.info("\nDone.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    run()
