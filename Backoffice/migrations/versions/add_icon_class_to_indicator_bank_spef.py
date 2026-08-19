"""Add icon_class to indicator_bank_spef (SP/EF catalog icons)

Revision ID: add_spef_icon_class
Revises: drop_notif_sound
Create Date: 2026-08-19
"""
from alembic import op
import sqlalchemy as sa


revision = "add_spef_icon_class"
down_revision = "drop_notif_sound"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("indicator_bank_spef", schema=None) as batch_op:
        batch_op.add_column(sa.Column("icon_class", sa.String(length=50), nullable=True))


def downgrade():
    with op.batch_alter_table("indicator_bank_spef", schema=None) as batch_op:
        batch_op.drop_column("icon_class")
