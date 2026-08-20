"""Add logo_filename to national_societies

Revision ID: add_ns_logo_file
Revises: add_spef_icon_file
Create Date: 2026-08-20
"""
from alembic import op
import sqlalchemy as sa


revision = "add_ns_logo_file"
down_revision = "add_spef_icon_file"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("national_societies", schema=None) as batch_op:
        batch_op.add_column(sa.Column("logo_filename", sa.String(length=255), nullable=True))


def downgrade():
    with op.batch_alter_table("national_societies", schema=None) as batch_op:
        batch_op.drop_column("logo_filename")
