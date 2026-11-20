"""Store the GO application on a baseline, and bank-match flags on the plan.

Revision ID: dref_monitoring_application
Revises: dref_monitoring_draft_pipeline
Create Date: 2026-11-20
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "dref_monitoring_application"
down_revision = "dref_monitoring_draft_pipeline"
branch_labels = None
depends_on = None


def _columns(insp, table: str) -> set[str]:
    if not insp.has_table(table):
        return set()
    return {column["name"] for column in insp.get_columns(table)}


def upgrade():
    bind = op.get_bind()
    insp = inspect(bind)
    baseline = _columns(insp, "dref_mon_baseline")
    if baseline and "application" not in baseline:
        op.add_column("dref_mon_baseline", sa.Column("application", sa.JSON(), nullable=True))
    group = _columns(insp, "dref_mon_group")
    if group and "bank_sector_id" not in group:
        op.add_column("dref_mon_group", sa.Column("bank_sector_id", sa.Integer(), nullable=True))
    if group and "unmatched" not in group:
        op.add_column(
            "dref_mon_group",
            sa.Column("unmatched", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    indicator = _columns(insp, "dref_mon_indicator")
    if indicator and "indicator_bank_id" not in indicator:
        op.add_column("dref_mon_indicator", sa.Column("indicator_bank_id", sa.Integer(), nullable=True))
    if indicator and "unmatched" not in indicator:
        op.add_column(
            "dref_mon_indicator",
            sa.Column("unmatched", sa.Boolean(), nullable=False, server_default=sa.false()),
        )


def downgrade():
    bind = op.get_bind()
    insp = inspect(bind)
    indicator = _columns(insp, "dref_mon_indicator")
    if "unmatched" in indicator:
        op.drop_column("dref_mon_indicator", "unmatched")
    if "indicator_bank_id" in indicator:
        op.drop_column("dref_mon_indicator", "indicator_bank_id")
    group = _columns(insp, "dref_mon_group")
    if "unmatched" in group:
        op.drop_column("dref_mon_group", "unmatched")
    if "bank_sector_id" in group:
        op.drop_column("dref_mon_group", "bank_sector_id")
    baseline = _columns(insp, "dref_mon_baseline")
    if "application" in baseline:
        op.drop_column("dref_mon_baseline", "application")
