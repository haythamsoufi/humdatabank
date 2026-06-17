"""Add dynamic_section_context table for binding dynamic sections to a stable external context

Revision ID: add_dynamic_section_context
Revises: add_dynamic_indicator_repeat_instance
Create Date: 2026-06-16

Stores a per-assignment binding between a dynamic section and a stable external key
(e.g. an emergency operation appeal code) so saved dynamic-indicator data stays
attributable to the same emergency even when the source API reorders or filters change.
"""

from alembic import op
import sqlalchemy as sa


revision = 'add_dynamic_section_context'
down_revision = 'add_dynamic_indicator_repeat_instance'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'dynamic_section_context',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('assignment_entity_status_id', sa.Integer(), nullable=True),
        sa.Column('public_submission_id', sa.Integer(), nullable=True),
        sa.Column('section_id', sa.Integer(), nullable=False),
        sa.Column('provider_id', sa.String(length=64), nullable=False),
        sa.Column('slot', sa.Integer(), nullable=True),
        sa.Column('context_key', sa.String(length=128), nullable=False),
        sa.Column('label_snapshot', sa.String(length=512), nullable=True),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='active'),
        sa.Column('filters_hash', sa.String(length=64), nullable=True),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('created_by_user_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['assignment_entity_status_id'], ['assignment_entity_status.id'], ),
        sa.ForeignKeyConstraint(['public_submission_id'], ['public_submission.id'], ),
        sa.ForeignKeyConstraint(['section_id'], ['form_section.id'], ),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['user.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('assignment_entity_status_id', 'section_id', 'provider_id', name='_dynamic_section_context_entity_unique'),
        sa.UniqueConstraint('public_submission_id', 'section_id', 'provider_id', name='_dynamic_section_context_public_unique'),
        sa.CheckConstraint(
            '(assignment_entity_status_id IS NOT NULL) OR (public_submission_id IS NOT NULL)',
            name='ck_dynamic_section_context_parent',
        ),
    )
    with op.batch_alter_table('dynamic_section_context', schema=None) as batch_op:
        batch_op.create_index('ix_dynamic_section_context_aes', ['assignment_entity_status_id'])
        batch_op.create_index('ix_dynamic_section_context_public', ['public_submission_id'])
        batch_op.create_index('ix_dynamic_section_context_section', ['section_id'])


def downgrade():
    with op.batch_alter_table('dynamic_section_context', schema=None) as batch_op:
        batch_op.drop_index('ix_dynamic_section_context_section')
        batch_op.drop_index('ix_dynamic_section_context_public')
        batch_op.drop_index('ix_dynamic_section_context_aes')
    op.drop_table('dynamic_section_context')
