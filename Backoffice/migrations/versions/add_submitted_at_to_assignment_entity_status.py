"""Add submitted_at to assignment_entity_status

Records the exact timestamp when a form's status was changed to 'Submitted'.
Unlike status_timestamp, this column is set once and never overwritten when
the status later moves to 'Approved', preserving both the submission and
approval timestamps independently.

Revision ID: add_submitted_at_to_aes
Revises: add_llm_quality_judge
Create Date: 2026-03-18

"""

from alembic import op
import sqlalchemy as sa

revision = 'add_submitted_at_to_aes'
down_revision = 'add_llm_quality_judge'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('assignment_entity_status', schema=None) as batch_op:
        batch_op.add_column(sa.Column('submitted_at', sa.DateTime(), nullable=True))
        batch_op.create_index('ix_aes_submitted_at', ['submitted_at'])


def downgrade():
    with op.batch_alter_table('assignment_entity_status', schema=None) as batch_op:
        batch_op.drop_index('ix_aes_submitted_at')
        batch_op.drop_column('submitted_at')
