"""Add area_label to indicator_bank_history when missing.

Revision ID: add_indicator_bank_history_area_label
Revises: add_indicator_bank_spef_lookups
Create Date: 2026-06-13

Some environments applied add_indicator_bank_spef_lookups before it also
updated indicator_bank_history. This migration is idempotent.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

revision = "add_indicator_bank_history_area_label"
down_revision = "add_indicator_bank_spef_lookups"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    column_exists = bind.execute(
        text(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_name = 'indicator_bank_history'
                  AND column_name = 'area_label'
            )
            """
        )
    ).scalar()
    if column_exists:
        return

    op.add_column(
        "indicator_bank_history",
        sa.Column("area_label", sa.Text(), nullable=True),
    )

    bind.execute(
        text(
            """
            UPDATE indicator_bank_history h
            SET area_label = s.name
            FROM indicator_bank_spef s
            WHERE h.area IS NOT NULL
              AND trim(h.area) <> ''
              AND upper(trim(h.area)) = upper(trim(s.code))
            """
        )
    )


def downgrade():
    bind = op.get_bind()
    column_exists = bind.execute(
        text(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_name = 'indicator_bank_history'
                  AND column_name = 'area_label'
            )
            """
        )
    ).scalar()
    if not column_exists:
        return
    op.drop_column("indicator_bank_history", "area_label")
