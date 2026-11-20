"""Remember the day a draft monitoring plan was last reminded.

Revision ID: dref_monitoring_plan_reminder
Revises: dref_monitoring_plan_shape
Create Date: 2026-11-19
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "dref_monitoring_plan_reminder"
down_revision = "dref_monitoring_plan_shape"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = inspect(bind)
    if not insp.has_table("dref_mon_plan"):
        return
    columns = {column["name"] for column in insp.get_columns("dref_mon_plan")}
    if "validation_reminded_on" not in columns:
        op.add_column("dref_mon_plan", sa.Column("validation_reminded_on", sa.Date(), nullable=True))


def downgrade():
    bind = op.get_bind()
    insp = inspect(bind)
    if not insp.has_table("dref_mon_plan"):
        return
    columns = {column["name"] for column in insp.get_columns("dref_mon_plan")}
    if "validation_reminded_on" in columns:
        op.drop_column("dref_mon_plan", "validation_reminded_on")
