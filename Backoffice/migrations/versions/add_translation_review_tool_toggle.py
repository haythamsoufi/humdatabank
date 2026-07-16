"""Add per-user opt-in toggle for the inline translation review tool

Revision ID: add_translation_review_tool_toggle
Revises: add_rbac_language_scope
Create Date: 2026-07-15 17:48:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'add_translation_review_tool_toggle'
down_revision = 'add_rbac_language_scope'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'user',
        sa.Column(
            'translation_review_tool_enabled',
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade():
    op.drop_column('user', 'translation_review_tool_enabled')
