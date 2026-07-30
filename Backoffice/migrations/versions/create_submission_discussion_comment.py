"""Create submission_discussion_comment table

Revision ID: create_submission_discussion_comment
Revises: add_enable_discussion
Create Date: 2026-07-30

Stores append-only discussion comments per assignment entity status or public submission.
"""
from alembic import op
import sqlalchemy as sa


revision = 'create_submission_discussion_comment'
down_revision = 'add_enable_discussion'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'submission_discussion_comment',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('assignment_entity_status_id', sa.Integer(), nullable=True),
        sa.Column('public_submission_id', sa.Integer(), nullable=True),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('created_by_user_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ['assignment_entity_status_id'],
            ['assignment_entity_status.id'],
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['public_submission_id'],
            ['public_submission.id'],
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['created_by_user_id'],
            ['user.id'],
            ondelete='SET NULL',
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_sdc_aes',
        'submission_discussion_comment',
        ['assignment_entity_status_id'],
    )
    op.create_index(
        'ix_sdc_public',
        'submission_discussion_comment',
        ['public_submission_id'],
    )


def downgrade():
    op.drop_index('ix_sdc_public', table_name='submission_discussion_comment')
    op.drop_index('ix_sdc_aes', table_name='submission_discussion_comment')
    op.drop_table('submission_discussion_comment')
