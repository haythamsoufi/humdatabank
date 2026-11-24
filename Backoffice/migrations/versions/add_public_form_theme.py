"""Add public_form_theme to assigned_form.

Admins can pick a visual theme (for example a campaign look) for the public link
of an assignment. Existing assignments keep the standard form (NULL).

Revision ID: add_public_form_theme
Revises: add_public_collect_submitter_info
Create Date: 2026-11-24

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "add_public_form_theme"
down_revision = "add_public_collect_submitter_info"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = inspect(bind)
    if not insp.has_table("assigned_form"):
        return
    cols = {c["name"] for c in insp.get_columns("assigned_form")}
    if "public_form_theme" in cols:
        return
    with op.batch_alter_table("assigned_form", schema=None) as batch_op:
        batch_op.add_column(sa.Column("public_form_theme", sa.String(length=50), nullable=True))


def downgrade():
    bind = op.get_bind()
    insp = inspect(bind)
    if not insp.has_table("assigned_form"):
        return
    cols = {c["name"] for c in insp.get_columns("assigned_form")}
    if "public_form_theme" not in cols:
        return
    with op.batch_alter_table("assigned_form", schema=None) as batch_op:
        batch_op.drop_column("public_form_theme")
