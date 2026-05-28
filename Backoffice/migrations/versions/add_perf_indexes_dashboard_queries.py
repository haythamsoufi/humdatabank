"""Add performance indexes for dashboard contributor and activity queries

Revision ID: add_perf_indexes_dashboard
Revises: add_indicator_bank_metadata
Create Date: 2026-05-28

The dashboard page fires two GROUP BY queries against entity_activity_log to
compute "last modified by" and "contributors" per assignment. Both filter on
  WHERE entity_type = ? AND entity_id = ? AND assignment_id IN (...)

The existing ix_entity_activity_entity_time(entity_type, entity_id, timestamp)
covers entity lookups but does not include assignment_id, so PostgreSQL falls
back to a full index scan + filter for the assignment_id IN clause.

This migration adds a composite covering index on
  (entity_type, entity_id, assignment_id)
so the planner can satisfy the WHERE clause from the index alone, then fetch
timestamp/user_id from the heap only for matching rows.
"""

from alembic import op

revision = "add_perf_indexes_dashboard"
down_revision = "add_indicator_bank_metadata"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("entity_activity_log", schema=None) as batch_op:
        batch_op.create_index(
            "ix_entity_activity_entity_assignment",
            ["entity_type", "entity_id", "assignment_id"],
            unique=False,
        )


def downgrade():
    with op.batch_alter_table("entity_activity_log", schema=None) as batch_op:
        batch_op.drop_index("ix_entity_activity_entity_assignment")
