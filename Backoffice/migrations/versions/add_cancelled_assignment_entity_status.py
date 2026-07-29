"""Add cancelled assignment entity status

Revision ID: add_cancelled_aes_status
Revises: widen_form_data_value_to_text
Create Date: 2026-07-29
"""

from alembic import op


revision = "add_cancelled_aes_status"
down_revision = "widen_form_data_value_to_text"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "ALTER TYPE assignmententitystatus ADD VALUE IF NOT EXISTS 'cancelled'"
    )


def downgrade():
    # PostgreSQL does not support removing enum values without rebuilding the type.
    pass
