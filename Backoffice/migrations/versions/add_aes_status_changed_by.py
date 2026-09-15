"""Add status_changed_by_user_id to assignment_entity_status

Revision ID: add_aes_status_changed_by
Revises: backfill_user_created_at_history
Create Date: 2026-09-15

Records the user who last set an entity's assignment status (any status).
Existing rows are backfilled from submitted/approved/sent-for-review actors
when those match the current status.
"""
from alembic import op
import sqlalchemy as sa


revision = 'add_aes_status_changed_by'
down_revision = 'backfill_user_created_at_history'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'assignment_entity_status',
        sa.Column('status_changed_by_user_id', sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        'fk_aes_status_changed_by_user',
        'assignment_entity_status',
        'user',
        ['status_changed_by_user_id'],
        ['id'],
        ondelete='SET NULL',
    )
    op.create_index(
        'ix_aes_status_changed_by',
        'assignment_entity_status',
        ['status_changed_by_user_id'],
    )
    op.execute(
        """
        UPDATE assignment_entity_status
        SET status_changed_by_user_id = CASE
            WHEN status::text = 'approved' THEN approved_by_user_id
            WHEN status::text = 'submitted' THEN submitted_by_user_id
            WHEN status::text = 'sent_for_review' THEN sent_for_review_by_user_id
            ELSE NULL
        END
        WHERE status_changed_by_user_id IS NULL
        """
    )


def downgrade():
    op.drop_index('ix_aes_status_changed_by', table_name='assignment_entity_status')
    op.drop_constraint('fk_aes_status_changed_by_user', 'assignment_entity_status', type_='foreignkey')
    op.drop_column('assignment_entity_status', 'status_changed_by_user_id')
