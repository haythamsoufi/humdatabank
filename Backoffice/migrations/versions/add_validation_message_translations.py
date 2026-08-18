"""Add validation_message_translations to form_item

Revision ID: add_val_msg_trans
Revises: add_translation_quality
Create Date: 2026-08-18
"""
from alembic import op
import sqlalchemy as sa


revision = "add_val_msg_trans"
down_revision = "add_translation_quality"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("form_item", schema=None) as batch_op:
        batch_op.add_column(sa.Column("validation_message_translations", sa.JSON(), nullable=True))


def downgrade():
    with op.batch_alter_table("form_item", schema=None) as batch_op:
        batch_op.drop_column("validation_message_translations")
