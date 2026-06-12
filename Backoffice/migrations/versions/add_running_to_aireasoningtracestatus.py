"""Add running to aireasoningtracestatus enum

Early agent trace rows are created with status=running before the run
completes. The batch enum migration omitted this value.

Revision ID: add_running_aireasoningtracestatus
Revises: align_aux_scalar_form_values
Create Date: 2026-06-11

"""
from alembic import op


revision = "add_running_aireasoningtracestatus"
down_revision = "align_aux_scalar_form_values"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "ALTER TYPE aireasoningtracestatus ADD VALUE IF NOT EXISTS 'running'"
    )


def downgrade():
    # PostgreSQL cannot drop individual enum values without recreating the type.
    pass
