"""Add source to submission_discussion_comment

Revision ID: add_sdc_source
Revises: create_submission_discussion_comment
Create Date: 2026-07-30

Tracks provenance for comments that lack an author (e.g. UPR Excel historical import).
"""
from alembic import op
import sqlalchemy as sa


revision = 'add_sdc_source'
down_revision = 'create_submission_discussion_comment'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('submission_discussion_comment', schema=None) as batch_op:
        batch_op.add_column(sa.Column('source', sa.String(length=64), nullable=True))


def downgrade():
    with op.batch_alter_table('submission_discussion_comment', schema=None) as batch_op:
        batch_op.drop_column('source')
