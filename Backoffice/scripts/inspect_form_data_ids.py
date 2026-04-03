import logging
import os
import sys

from sqlalchemy import text

logger = logging.getLogger(__name__)

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app import create_app, db  # noqa: E402


def _mask_db_uri(uri: str) -> str:
    if not uri:
        return "<not set>"
    # Basic masking: redact anything after '@' (password/host)
    try:
        if "@" in uri:
            return uri.split("@", 1)[0] + "@<redacted>"
    except Exception as e:
        logger.debug("_mask_db_uri fallback: %s", e)
    return "<set>"


def main() -> None:
    ids = (149282, 151691)

    app = create_app(os.getenv("FLASK_CONFIG"))
    uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
    logger.info("SQLALCHEMY_DATABASE_URI = %s", _mask_db_uri(uri))

    with app.app_context():
        sql = text(
            """
            select
              id,
              assignment_entity_status_id,
              public_submission_id,
              form_item_id,
              value,
              disagg_data::text as disagg_text,
              (disagg_data is null) as disagg_is_sql_null,
              (disagg_data::text = 'null') as disagg_is_json_null,
              prefilled_value::text as prefilled_value_text,
              (prefilled_value is null) as prefilled_value_is_sql_null,
              (prefilled_value::text = 'null') as prefilled_value_is_json_null,
              prefilled_disagg_data::text as prefilled_disagg_text,
              (prefilled_disagg_data is null) as prefilled_disagg_is_sql_null,
              (prefilled_disagg_data::text = 'null') as prefilled_disagg_is_json_null,
              imputed_value::text as imputed_value_text,
              (imputed_value is null) as imputed_value_is_sql_null,
              (imputed_value::text = 'null') as imputed_value_is_json_null,
              imputed_disagg_data::text as imputed_disagg_text,
              (imputed_disagg_data is null) as imputed_disagg_is_sql_null,
              (imputed_disagg_data::text = 'null') as imputed_disagg_is_json_null,
              data_not_available,
              not_applicable,
              submitted_at
            from form_data
            where id = any(:ids)
            order by id
            """
        )
        rows = db.session.execute(sql, {"ids": list(ids)}).mappings().all()

        logger.info("ROWS=")
        for r in rows:
            logger.info("%s", dict(r))

        # Show all rows for the same (assignment_entity_status_id, form_item_id)
        # for quick duplicate diagnosis.
        aes = None
        fi = None
        for r in rows:
            if r.get("assignment_entity_status_id") and r.get("form_item_id"):
                aes = int(r["assignment_entity_status_id"])
                fi = int(r["form_item_id"])
                break

        if aes and fi:
            sql2 = text(
                """
                select
                  id,
                  submitted_at,
                  value,
                  disagg_data::text as disagg_text,
                  prefilled_value::text as prefilled_value_text,
                  imputed_value::text as imputed_value_text,
                  data_not_available,
                  not_applicable
                from form_data
                where assignment_entity_status_id = :aes
                  and form_item_id = :fi
                order by id
                """
            )
            allrows = db.session.execute(sql2, {"aes": aes, "fi": fi}).mappings().all()
            logger.info("ALL_FOR_(aes,fi)= %s", (aes, fi))
            for r in allrows:
                logger.info("%s", dict(r))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    main()

