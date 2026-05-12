"""Add unique constraint on assigned_form(template_id, period_name) to prevent duplicate race.

Revision ID: uq_assigned_form_template_period
Revises: add_user_external_id
Create Date: 2026-05-08
"""

from alembic import op
import sqlalchemy as sa

revision = 'uq_assigned_form_template_period'
down_revision = 'add_user_external_id'
branch_labels = None
depends_on = None


def upgrade():
    # Remove duplicate rows before adding the constraint (keep the first by id).
    op.execute("""
        DELETE FROM assigned_form
        WHERE id NOT IN (
            SELECT MIN(id)
            FROM assigned_form
            GROUP BY template_id, period_name
        )
    """)
    op.create_unique_constraint(
        'uq_assigned_form_template_period',
        'assigned_form',
        ['template_id', 'period_name']
    )


def downgrade():
    op.drop_constraint(
        'uq_assigned_form_template_period',
        'assigned_form',
        type_='unique'
    )
