"""Store Draft 0 language, milestone link, validation, and the GO submission.

Revision ID: dref_monitoring_draft_pipeline
Revises: dref_monitoring_plan_reminder
Create Date: 2026-11-20
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "dref_monitoring_draft_pipeline"
down_revision = "dref_monitoring_plan_reminder"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = inspect(bind)
    if not insp.has_table("dref_mon_draft"):
        return
    columns = {column["name"] for column in insp.get_columns("dref_mon_draft")}
    additions = [
        ("language", sa.Column("language", sa.String(length=8), nullable=False, server_default="en")),
        ("trigger", sa.Column("trigger", sa.String(length=32), nullable=False, server_default="manual")),
        ("period_id", sa.Column("period_id", sa.Integer(), nullable=True)),
        ("status", sa.Column("status", sa.String(length=16), nullable=False, server_default="draft")),
        ("validated_at", sa.Column("validated_at", sa.DateTime(), nullable=True)),
        ("validated_by_user_id", sa.Column("validated_by_user_id", sa.Integer(), nullable=True)),
        ("go_status", sa.Column("go_status", sa.String(length=16), nullable=False, server_default="")),
        ("go_reference", sa.Column("go_reference", sa.String(length=64), nullable=False, server_default="")),
        ("go_error", sa.Column("go_error", sa.Text(), nullable=False, server_default="")),
        ("go_submitted_at", sa.Column("go_submitted_at", sa.DateTime(), nullable=True)),
    ]
    for name, column in additions:
        if name not in columns:
            op.add_column("dref_mon_draft", column)
    indexes = {index["name"] for index in insp.get_indexes("dref_mon_draft")}
    if "ix_dref_mon_draft_period" not in indexes:
        op.create_index(
            "ix_dref_mon_draft_period",
            "dref_mon_draft",
            ["operation_id", "period_id", "report_kind"],
        )


def downgrade():
    bind = op.get_bind()
    insp = inspect(bind)
    if not insp.has_table("dref_mon_draft"):
        return
    indexes = {index["name"] for index in insp.get_indexes("dref_mon_draft")}
    if "ix_dref_mon_draft_period" in indexes:
        op.drop_index("ix_dref_mon_draft_period", table_name="dref_mon_draft")
    columns = {column["name"] for column in insp.get_columns("dref_mon_draft")}
    for name in (
        "go_submitted_at",
        "go_error",
        "go_reference",
        "go_status",
        "validated_by_user_id",
        "validated_at",
        "status",
        "period_id",
        "trigger",
        "language",
    ):
        if name in columns:
            op.drop_column("dref_mon_draft", name)
