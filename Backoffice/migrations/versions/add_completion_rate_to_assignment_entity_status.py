"""Add completion_rate to assignment_entity_status

Revision ID: add_aes_completion_rate
Revises: add_sdc_source
Create Date: 2026-07-30

Denormalized cache of assignment completion percentage (same formula as
AssignmentCompletionService). Populated on save and via
``flask backfill-completion-rates`` for existing rows (not during upgrade —
see note in upgrade()).
"""
from alembic import op
import sqlalchemy as sa


revision = 'add_aes_completion_rate'
down_revision = 'add_sdc_source'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'assignment_entity_status',
        sa.Column('completion_rate', sa.Numeric(precision=5, scale=1), nullable=True),
    )
    # Intentionally no data backfill here: per-row recompute is slow on large DBs
    # (one filled-item query per assignment_entity_status row). NULL rows are filled
    # lazily on read via AssignmentCompletionService.stored_rate_for, or in bulk via:
    #   flask backfill-completion-rates [--batch-size 500]


def downgrade():
    op.drop_column('assignment_entity_status', 'completion_rate')
