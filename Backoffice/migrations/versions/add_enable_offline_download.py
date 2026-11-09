"""Add enable_offline_download to assigned_form.

Every assignment starts with offline download off, including rows that
already exist. An admin opts in per assignment.

Revision ID: add_enable_offline_download
Revises: add_assigned_form_scope_project
Create Date: 2026-11-09

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "add_enable_offline_download"
down_revision = "add_assigned_form_scope_project"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = inspect(bind)
    if not insp.has_table("assigned_form"):
        return
    cols = {c["name"] for c in insp.get_columns("assigned_form")}
    if "enable_offline_download" not in cols:
        with op.batch_alter_table("assigned_form", schema=None) as batch_op:
            batch_op.add_column(
                sa.Column(
                    "enable_offline_download",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.false(),
                )
            )
    # Cover a column added by an earlier draft of this revision that defaulted
    # existing rows to true. Offline download stays off until an admin opts in.
    op.execute("UPDATE assigned_form SET enable_offline_download = FALSE")


def downgrade():
    bind = op.get_bind()
    insp = inspect(bind)
    if not insp.has_table("assigned_form"):
        return
    cols = {c["name"] for c in insp.get_columns("assigned_form")}
    if "enable_offline_download" not in cols:
        return
    with op.batch_alter_table("assigned_form", schema=None) as batch_op:
        batch_op.drop_column("enable_offline_download")
