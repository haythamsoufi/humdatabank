"""Emergency Appeal plans: switch indicators on or off, and start reporting when the plan is confirmed.

Revision ID: dref_monitoring_appeal_plan
Revises: add_public_form_theme
Create Date: 2026-11-24
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "dref_monitoring_appeal_plan"
down_revision = "add_public_form_theme"
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
    if indicator and "enabled" not in indicator:
        op.add_column(
            "dref_mon_indicator",
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        )
    operation = _columns(insp, "dref_mon_operation")
    if operation and "reporting_start" not in operation:
        op.add_column("dref_mon_operation", sa.Column("reporting_start", sa.Date(), nullable=True))


def downgrade():
    bind = op.get_bind()
    insp = inspect(bind)
    if "reporting_start" in _columns(insp, "dref_mon_operation"):
        op.drop_column("dref_mon_operation", "reporting_start")
    if "enabled" in _columns(insp, "dref_mon_indicator"):
        op.drop_column("dref_mon_indicator", "enabled")
