"""Add National Society (ns) unit and backfill old NS references.

This unit was a valid free-text value before the central catalog; the first
lookup migration did not include it, so some rows were left without a FK
and the denormalized unit string was cleared in some cases.

Revision ID: add_ns_indicator_bank_unit
Revises: add_indicator_bank_measurement_lookups
Create Date: 2026-04-22
"""

from __future__ import annotations

import datetime

from alembic import op
from sqlalchemy import text

revision = "add_ns_indicator_bank_unit"
down_revision = "add_indicator_bank_measurement_lookups"
branch_labels = None
depends_on = None


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def upgrade():
    now = _now()
    bind = op.get_bind()

    # Idempotent: insert "National Society" with stable code "ns" if missing.
    row = bind.execute(
        text("SELECT id FROM indicator_bank_unit WHERE lower(code) = 'ns' LIMIT 1")
    ).fetchone()
    if not row:
        bind.execute(
            text(
                "INSERT INTO indicator_bank_unit (code, name, name_translations, sort_order, is_active, allows_disaggregation, created_at, updated_at) "
                "VALUES ('ns', 'National Society', NULL, 35, true, false, :ca, :ua)"
            ),
            {"ca": now, "ua": now},
        )
    unit_id = bind.execute(
        text("SELECT id FROM indicator_bank_unit WHERE lower(code) = 'ns' LIMIT 1")
    ).scalar()
    if not unit_id:
        raise RuntimeError("add_ns_indicator_bank_unit: could not resolve ns row id")

    # Still have NS in the text column
    bind.execute(
        text(
            """
            UPDATE indicator_bank
            SET indicator_unit_id = :uid, unit = 'ns'
            WHERE lower(trim(COALESCE(unit, ''))) IN
              ('ns', 'n.s.', 'n.s', 'ns.', 'n.s', 'national society')
            """
        ),
        {"uid": unit_id},
    )
    # Current row was cleared but the most recent *overall* history snapshot still has NS
    bind.execute(
        text(
            """
            UPDATE indicator_bank ib
            SET indicator_unit_id = :uid, unit = 'ns'
            FROM (
                SELECT DISTINCT ON (indicator_bank_id) indicator_bank_id, unit AS hist_unit
                FROM indicator_bank_history
                ORDER BY indicator_bank_id, created_at DESC
            ) h
            WHERE ib.id = h.indicator_bank_id
              AND (ib.unit IS NULL OR btrim(COALESCE(ib.unit, '')) = '')
              AND lower(trim(COALESCE(h.hist_unit::text, ''))) IN
                ('ns', 'n.s.', 'n.s', 'ns.', 'national society')
            """
        ),
        {"uid": unit_id},
    )

    # Form items: string match, then sync from bank
    bind.execute(
        text(
            """
            UPDATE form_item
            SET indicator_unit_id = :uid, unit = 'ns'
            WHERE item_type = 'indicator'
              AND lower(trim(COALESCE(unit, ''))) IN ('ns', 'n.s.', 'n.s', 'n.s', 'ns.', 'ns')
            """
        ),
        {"uid": unit_id},
    )
    bind.execute(
        text(
            """
            UPDATE form_item fi
            SET indicator_unit_id = ib.indicator_unit_id,
                unit = ib.unit
            FROM indicator_bank ib
            WHERE fi.item_type = 'indicator'
              AND fi.indicator_bank_id = ib.id
              AND ib.indicator_unit_id = :uid
            """
        ),
        {"uid": unit_id},
    )


def downgrade():
    bind = op.get_bind()
    row = bind.execute(
        text("SELECT id FROM indicator_bank_unit WHERE lower(code) = 'ns' LIMIT 1")
    ).fetchone()
    if not row:
        return
    unit_id = row[0]
    # Clear only rows that were matched to this unit (soft downgrade)
    bind.execute(
        text(
            """
            UPDATE indicator_bank
            SET indicator_unit_id = NULL, unit = NULL
            WHERE indicator_unit_id = :uid
            """
        ),
        {"uid": unit_id},
    )
    bind.execute(
        text(
            """
            UPDATE form_item
            SET indicator_unit_id = NULL, unit = NULL
            WHERE item_type = 'indicator' AND indicator_unit_id = :uid
            """
        ),
        {"uid": unit_id},
    )
    bind.execute(
        text("DELETE FROM indicator_bank_unit WHERE id = :uid"),
        {"uid": unit_id},
    )
