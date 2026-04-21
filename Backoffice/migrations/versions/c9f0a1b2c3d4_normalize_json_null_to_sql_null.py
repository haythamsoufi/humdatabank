"""Normalize JSON literal null to SQL NULL

Revision ID: c9f0a1b2c3d4
Revises: b6c8a1f3d2e4
Create Date: 2026-02-15

Problem:
- PostgreSQL JSON/JSONB supports a JSON literal `null` value that is distinct from SQL NULL.
- Historical code paths created placeholder rows and/or wrote Python None into JSON columns, which
  could persist as JSON literal `null` (e.g., disagg_data = 'null'::jsonb) instead of SQL NULL.

Goal:
- Convert JSON literal `null` values to real SQL NULL for relevant columns.
"""

from alembic import op


revision = "c9f0a1b2c3d4"
down_revision = "b6c8a1f3d2e4"
branch_labels = None
depends_on = None


def upgrade():
    # form_data JSON columns
    op.execute("UPDATE form_data SET disagg_data = NULL WHERE disagg_data::text = 'null'")
    op.execute("UPDATE form_data SET prefilled_value = NULL WHERE prefilled_value::text = 'null'")
    op.execute("UPDATE form_data SET prefilled_disagg_data = NULL WHERE prefilled_disagg_data::text = 'null'")
    op.execute("UPDATE form_data SET imputed_value = NULL WHERE imputed_value::text = 'null'")
    op.execute("UPDATE form_data SET imputed_disagg_data = NULL WHERE imputed_disagg_data::text = 'null'")

    # Related JSON columns used for non-main sections
    op.execute("UPDATE dynamic_indicator_data SET disagg_data = NULL WHERE disagg_data::text = 'null'")
    op.execute("UPDATE repeat_group_data SET disagg_data = NULL WHERE disagg_data::text = 'null'")


def downgrade():
    # Not safely reversible: SQL NULL cannot be distinguished from "was JSON null" historically.
    pass

