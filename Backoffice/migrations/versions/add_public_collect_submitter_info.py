"""Add public_collect_submitter_info to assigned_form.

Public forms asked every submitter for a name and email. Admins can now turn
that off per assignment. Existing assignments keep asking (default true).

Revision ID: add_public_collect_submitter_info
Revises: public_submission_country_nullable
Create Date: 2026-11-24

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "add_public_collect_submitter_info"
down_revision = "public_submission_country_nullable"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = inspect(bind)
    if not insp.has_table("assigned_form"):
        return
    cols = {c["name"] for c in insp.get_columns("assigned_form")}
    if "public_collect_submitter_info" in cols:
        return
    with op.batch_alter_table("assigned_form", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "public_collect_submitter_info",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            )
        )


def downgrade():
    bind = op.get_bind()
    insp = inspect(bind)
    if not insp.has_table("assigned_form"):
        return
    cols = {c["name"] for c in insp.get_columns("assigned_form")}
    if "public_collect_submitter_info" not in cols:
        return
    with op.batch_alter_table("assigned_form", schema=None) as batch_op:
        batch_op.drop_column("public_collect_submitter_info")
