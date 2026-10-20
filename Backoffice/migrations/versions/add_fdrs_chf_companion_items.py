"""Add Swiss-franc companion items for FDRS income and expenditure.

The visible indicator keeps the amount in the reporting currency. A second
form item, excluded from completion, stores the Swiss-franc figure. Existing
values were imported as Swiss francs, so they are copied onto the companion
and the visible indicator's FDRS code becomes the local-currency KPI.

Revision ID: fdrs_chf_companion_items
Revises: add_resource_external_url
"""

from __future__ import annotations

import json
import uuid

import sqlalchemy as sa
from alembic import op

revision = "fdrs_chf_companion_items"
down_revision = "add_resource_external_url"
branch_labels = None
depends_on = None

# (local code on the visible item, Swiss-franc code on the companion)
_PAIRS = (
    ("KPI_IncomeLC", "KPI_IncomeLC_CHF"),
    ("KPI_expenditureLC", "KPI_expenditureLC_CHF"),
)
_CHF_NAMESPACE = uuid.UUID("6f0c1b7e-4a2d-4f1a-9c3e-8b7d5a1e0c44")


def _as_dict(value):
    if not value:
        return {}
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return dict(parsed) if isinstance(parsed, dict) else {}
    if isinstance(value, dict):
        return dict(value)
    return {}


def _one(bind, sql, **params):
    return bind.execute(sa.text(sql), params).mappings().first()


def _ensure_banks(bind, indicator_bank, local_code, chf_code):
    """Keep the shared CHF indicator. Add a separate bank row for the local code.

    Income and expenditure indicators are used by more than FDRS. Their existing
    ``fdrs_kpi_code`` stays the Swiss-franc KPI. Only template 21's visible items
    are pointed at the new reporting-currency row.
    """
    chf_row = _one(bind, "SELECT * FROM indicator_bank WHERE fdrs_kpi_code = :code", code=chf_code)
    local_row = _one(bind, "SELECT * FROM indicator_bank WHERE fdrs_kpi_code = :code", code=local_code)
    if chf_row is None:
        return None, None
    if local_row is None:
        clone = dict(chf_row)
        clone.pop("id", None)
        clone["name"] = f"{chf_row['name']} (reporting currency)"
        clone["fdrs_kpi_code"] = local_code
        local_id = bind.execute(sa.insert(indicator_bank).values(**clone).returning(indicator_bank.c.id)).scalar()
        return local_id, chf_row["id"]
    return local_row["id"], chf_row["id"]


def _companion_exists(bind, version_id, source_id):
    rows = bind.execute(
        sa.text(
            """
            SELECT id, config
            FROM form_item
            WHERE version_id = :version_id
              AND archived IS FALSE
            """
        ),
        {"version_id": version_id},
    ).mappings()
    for row in rows:
        config = _as_dict(row["config"])
        if config.get("fdrs_chf_companion") and int(config.get("fdrs_chf_source_item_id") or 0) == int(source_id):
            return True
    return False


def _copy_form_data(bind, source_id, companion_id):
    insp = sa.inspect(bind)
    columns = [col["name"] for col in insp.get_columns("form_data") if col["name"] != "id"]
    select_list = []
    for name in columns:
        if name == "form_item_id":
            select_list.append(":companion_id AS form_item_id")
        else:
            select_list.append(f"src.{name}")
    sql = f"""
        INSERT INTO form_data ({", ".join(columns)})
        SELECT {", ".join(select_list)}
        FROM form_data AS src
        WHERE src.form_item_id = :source_id
          AND NOT EXISTS (
              SELECT 1
              FROM form_data AS dst
              WHERE dst.form_item_id = :companion_id
                AND dst.assignment_entity_status_id IS NOT DISTINCT FROM src.assignment_entity_status_id
                AND dst.public_submission_id IS NOT DISTINCT FROM src.public_submission_id
          )
    """
    bind.execute(sa.text(sql), {"source_id": source_id, "companion_id": companion_id})


def _ensure_companions(bind, form_item, local_bank_id, chf_bank_id):
    sources = bind.execute(
        sa.text(
            """
            SELECT * FROM form_item
            WHERE indicator_bank_id = :bank_id
              AND template_id = 21
              AND archived IS FALSE
            """
        ),
        {"bank_id": chf_bank_id},
    ).mappings()
    for source in sources:
        config = _as_dict(source["config"])
        if config.get("fdrs_chf_companion"):
            continue
        if _companion_exists(bind, source["version_id"], source["id"]):
            bind.execute(
                sa.text("UPDATE form_item SET indicator_bank_id = :bank_id WHERE id = :id"),
                {"bank_id": local_bank_id, "id": source["id"]},
            )
            continue
        companion = dict(source)
        companion.pop("id", None)
        companion["indicator_bank_id"] = chf_bank_id
        companion["label"] = f"{source['label']} (CHF)"
        companion["relevance_condition"] = None
        order = source["order"] if source["order"] is not None else 0
        companion["order"] = float(order) + 0.01
        seed = source["stable_key"] or f"item-{source['id']}"
        companion["stable_key"] = str(uuid.uuid5(_CHF_NAMESPACE, f"fdrs-chf:{seed}"))
        config["is_required"] = False
        config["exclude_from_completion_rate"] = True
        config["fdrs_chf_companion"] = True
        config["fdrs_chf_source_item_id"] = int(source["id"])
        companion["config"] = config
        companion["archived"] = False
        new_id = bind.execute(sa.insert(form_item).values(**companion).returning(form_item.c.id)).scalar()
        _copy_form_data(bind, source["id"], new_id)
        bind.execute(
            sa.text("UPDATE form_item SET indicator_bank_id = :bank_id WHERE id = :id"),
            {"bank_id": local_bank_id, "id": source["id"]},
        )


def _flag_income_matrix(bind):
    rows = bind.execute(
        sa.text(
            """
            SELECT id, config, label
            FROM form_item
            WHERE archived IS FALSE
              AND item_type = 'matrix'
              AND template_id = 21
            """
        )
    ).mappings()
    for row in rows:
        label = (row["label"] or "").lower()
        if "income" not in label or "source" not in label:
            continue
        config = _as_dict(row["config"])
        if config.get("fdrs_income_sources"):
            continue
        config["fdrs_income_sources"] = True
        bind.execute(
            sa.text("UPDATE form_item SET config = CAST(:config AS json) WHERE id = :id"),
            {"config": json.dumps(config), "id": row["id"]},
        )


def upgrade():
    bind = op.get_bind()
    meta = sa.MetaData()
    indicator_bank = sa.Table("indicator_bank", meta, autoload_with=bind)
    form_item = sa.Table("form_item", meta, autoload_with=bind)
    for local_code, chf_code in _PAIRS:
        local_bank_id, chf_bank_id = _ensure_banks(bind, indicator_bank, local_code, chf_code)
        if local_bank_id is None or chf_bank_id is None:
            continue
        _ensure_companions(bind, form_item, local_bank_id, chf_bank_id)
    _flag_income_matrix(bind)


def downgrade():
    bind = op.get_bind()
    companions = bind.execute(
        sa.text(
            """
            SELECT id, config
            FROM form_item
            WHERE config IS NOT NULL
            """
        )
    ).mappings()
    companion_ids = []
    for row in companions:
        config = _as_dict(row["config"])
        if config.get("fdrs_chf_companion"):
            companion_ids.append(row["id"])
    if companion_ids:
        bind.execute(
            sa.text("DELETE FROM form_data WHERE form_item_id IN :ids").bindparams(
                sa.bindparam("ids", expanding=True)
            ),
            {"ids": companion_ids},
        )
        bind.execute(
            sa.text("DELETE FROM form_item WHERE id IN :ids").bindparams(sa.bindparam("ids", expanding=True)),
            {"ids": companion_ids},
        )
    for local_code, chf_code in _PAIRS:
        local_row = _one(
            bind,
            "SELECT id FROM indicator_bank WHERE fdrs_kpi_code = :code AND name LIKE :suffix",
            code=local_code,
            suffix="% (reporting currency)",
        )
        chf_row = _one(bind, "SELECT id FROM indicator_bank WHERE fdrs_kpi_code = :code", code=chf_code)
        if local_row is not None and chf_row is not None:
            bind.execute(
                sa.text(
                    """
                    UPDATE form_item
                    SET indicator_bank_id = :chf_id
                    WHERE indicator_bank_id = :local_id
                      AND template_id = 21
                    """
                ),
                {"chf_id": chf_row["id"], "local_id": local_row["id"]},
            )
            bind.execute(sa.text("DELETE FROM indicator_bank WHERE id = :id"), {"id": local_row["id"]})
