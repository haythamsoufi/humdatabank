"""Replace SPEF icon_class with uploaded icon_filename

Revision ID: add_spef_icon_file
Revises: add_spef_icon_class
Create Date: 2026-08-19
"""
from alembic import op
import sqlalchemy as sa


revision = "add_spef_icon_file"
down_revision = "add_spef_icon_class"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("indicator_bank_spef", schema=None) as batch_op:
        batch_op.drop_column("icon_class")
        batch_op.add_column(sa.Column("icon_filename", sa.String(length=255), nullable=True))


def downgrade():
    with op.batch_alter_table("indicator_bank_spef", schema=None) as batch_op:
        batch_op.drop_column("icon_filename")
        batch_op.add_column(sa.Column("icon_class", sa.String(length=50), nullable=True))
