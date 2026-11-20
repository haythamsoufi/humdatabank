"""Flag indicator-bank links made by the temporary GO title adapter.

Revision ID: dref_monitoring_indicator_adapter
Revises: dref_monitoring_application
Create Date: 2026-11-20
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "dref_monitoring_indicator_adapter"
down_revision = "dref_monitoring_application"
branch_labels = None
depends_on = None


def _columns(insp, table: str) -> set[str]:
    if not insp.has_table(table):
        return set()
    return {column["name"] for column in insp.get_columns(table)}


def upgrade():
    bind = op.get_bind()
    insp = inspect(bind)
    indicator = _columns(insp, "dref_mon_indicator")
    if indicator and "bank_adapted" not in indicator:
        op.add_column(
            "dref_mon_indicator",
            sa.Column("bank_adapted", sa.Boolean(), nullable=False, server_default=sa.false()),
        )


def downgrade():
    bind = op.get_bind()
    insp = inspect(bind)
    indicator = _columns(insp, "dref_mon_indicator")
    if "bank_adapted" in indicator:
        op.drop_column("dref_mon_indicator", "bank_adapted")
