"""Add sent_for_review status and NS review workflow columns

Revision ID: add_sent_for_review_workflow
Revises: normalize_status_enum_casing
Create Date: 2026-06-03
"""

from alembic import op
import sqlalchemy as sa


revision = 'add_sent_for_review_workflow'
down_revision = 'normalize_status_enum_casing'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TYPE assignmententitystatus ADD VALUE IF NOT EXISTS 'sent_for_review'")

    op.add_column(
        'assigned_form',
        sa.Column('requires_delegation_review', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.alter_column('assigned_form', 'requires_delegation_review', server_default=None)

    op.add_column('assignment_entity_status', sa.Column('sent_for_review_by_user_id', sa.Integer(), nullable=True))
    op.add_column('assignment_entity_status', sa.Column('sent_for_review_at', sa.DateTime(), nullable=True))
    op.create_foreign_key(
        'fk_aes_sent_for_review_by_user',
        'assignment_entity_status',
        'user',
        ['sent_for_review_by_user_id'],
        ['id'],
        ondelete='SET NULL',
    )
    op.create_index('ix_aes_sent_for_review_by', 'assignment_entity_status', ['sent_for_review_by_user_id'])
    op.create_index('ix_aes_sent_for_review_at', 'assignment_entity_status', ['sent_for_review_at'])


def downgrade():
    op.drop_index('ix_aes_sent_for_review_at', table_name='assignment_entity_status')
    op.drop_index('ix_aes_sent_for_review_by', table_name='assignment_entity_status')
    op.drop_constraint('fk_aes_sent_for_review_by_user', 'assignment_entity_status', type_='foreignkey')
    op.drop_column('assignment_entity_status', 'sent_for_review_at')
    op.drop_column('assignment_entity_status', 'sent_for_review_by_user_id')
    op.drop_column('assigned_form', 'requires_delegation_review')
    # PostgreSQL does not support removing enum values without rebuilding the type; left in place on downgrade.
