"""Link DREF operations to projects and periods to report cycles.

Revision ID: dref_monitoring_project_links
Revises: add_project_assignment
Create Date: 2026-11-19
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "dref_monitoring_project_links"
down_revision = "add_project_assignment"
branch_labels = None
depends_on = None


def _columns(insp, table: str) -> set[str]:
    if not insp.has_table(table):
        return set()
    return {column["name"] for column in insp.get_columns(table)}


def upgrade():
    bind = op.get_bind()
    insp = inspect(bind)
    operation_cols = _columns(insp, "dref_mon_operation")
    if operation_cols and "project_id" not in operation_cols:
        op.add_column("dref_mon_operation", sa.Column("project_id", sa.Integer(), nullable=True))
        op.create_foreign_key(
            "fk_dref_mon_operation_project",
            "dref_mon_operation",
            "project",
            ["project_id"],
            ["id"],
            ondelete="SET NULL",
        )
        op.create_index("ix_dref_mon_operation_project", "dref_mon_operation", ["project_id"])

    period_cols = _columns(insp, "dref_mon_period")
    if period_cols and "assigned_form_id" not in period_cols:
        op.add_column("dref_mon_period", sa.Column("assigned_form_id", sa.Integer(), nullable=True))
        op.create_foreign_key(
            "fk_dref_mon_period_assigned_form",
            "dref_mon_period",
            "assigned_form",
            ["assigned_form_id"],
            ["id"],
            ondelete="SET NULL",
        )
        op.create_index("ix_dref_mon_period_assignment", "dref_mon_period", ["assigned_form_id"])


def downgrade():
    bind = op.get_bind()
    insp = inspect(bind)
    if "assigned_form_id" in _columns(insp, "dref_mon_period"):
        op.drop_index("ix_dref_mon_period_assignment", table_name="dref_mon_period")
        op.drop_constraint("fk_dref_mon_period_assigned_form", "dref_mon_period", type_="foreignkey")
        op.drop_column("dref_mon_period", "assigned_form_id")
    if "project_id" in _columns(insp, "dref_mon_operation"):
        op.drop_index("ix_dref_mon_operation_project", table_name="dref_mon_operation")
        op.drop_constraint("fk_dref_mon_operation_project", "dref_mon_operation", type_="foreignkey")
        op.drop_column("dref_mon_operation", "project_id")
