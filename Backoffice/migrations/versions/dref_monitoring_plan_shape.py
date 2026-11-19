"""Sector indicators own activities, and reports store a disaggregation flag.

Revision ID: dref_monitoring_plan_shape
Revises: dref_monitoring_project_links
Create Date: 2026-11-19
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "dref_monitoring_plan_shape"
down_revision = "dref_monitoring_project_links"
branch_labels = None
depends_on = None


def _columns(insp, table: str) -> set[str]:
    if not insp.has_table(table):
        return set()
    return {column["name"] for column in insp.get_columns(table)}


def upgrade():
    bind = op.get_bind()
    insp = inspect(bind)
    activity_cols = _columns(insp, "dref_mon_activity")
    if activity_cols and "target" not in activity_cols:
        op.add_column("dref_mon_activity", sa.Column("target", sa.Numeric(14, 2), nullable=True))
    if activity_cols and "activity_type" not in activity_cols:
        op.add_column(
            "dref_mon_activity",
            sa.Column("activity_type", sa.String(length=64), nullable=False, server_default=""),
        )
    if activity_cols and "carried_out_by" not in activity_cols:
        op.add_column(
            "dref_mon_activity",
            sa.Column("carried_out_by", sa.String(length=64), nullable=False, server_default=""),
        )
    if activity_cols and "indicator_id" not in activity_cols:
        op.add_column("dref_mon_activity", sa.Column("indicator_id", sa.Integer(), nullable=True))
        op.create_foreign_key(
            "fk_dref_mon_activity_indicator",
            "dref_mon_activity",
            "dref_mon_indicator",
            ["indicator_id"],
            ["id"],
            ondelete="SET NULL",
        )
        op.create_index("ix_dref_mon_activity_indicator", "dref_mon_activity", ["indicator_id"])

    update_cols = _columns(insp, "dref_mon_activity_update")
    if update_cols and "disaggregation_na" not in update_cols:
        op.add_column(
            "dref_mon_activity_update",
            sa.Column("disaggregation_na", sa.Boolean(), nullable=False, server_default=sa.false()),
        )

    if activity_cols:
        op.execute(
            """
            UPDATE dref_mon_activity
            SET indicator_id = (
                SELECT id FROM dref_mon_indicator
                WHERE dref_mon_indicator.activity_id = dref_mon_activity.id
                ORDER BY id
                LIMIT 1
            )
            WHERE indicator_id IS NULL
            """
        )


def downgrade():
    bind = op.get_bind()
    insp = inspect(bind)
    update_cols = _columns(insp, "dref_mon_activity_update")
    if "disaggregation_na" in update_cols:
        op.drop_column("dref_mon_activity_update", "disaggregation_na")
    activity_cols = _columns(insp, "dref_mon_activity")
    if "indicator_id" in activity_cols:
        op.drop_index("ix_dref_mon_activity_indicator", table_name="dref_mon_activity")
        op.drop_constraint("fk_dref_mon_activity_indicator", "dref_mon_activity", type_="foreignkey")
        op.drop_column("dref_mon_activity", "indicator_id")
    if "carried_out_by" in activity_cols:
        op.drop_column("dref_mon_activity", "carried_out_by")
    if "activity_type" in activity_cols:
        op.drop_column("dref_mon_activity", "activity_type")
    if "target" in activity_cols:
        op.drop_column("dref_mon_activity", "target")
