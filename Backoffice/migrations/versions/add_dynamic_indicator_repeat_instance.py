"""Add repeat_instance_number to dynamic_indicator_data for per-repeat-entry indicators

Revision ID: add_dynamic_indicator_repeat_instance
Revises: add_validation_admin_permissions
Create Date: 2026-06-16

Allows dynamic indicators to be scoped to a specific repeat-group entry instance.
NULL = section-level (no repeat parent), integer = linked to that repeat instance number.

The existing unique constraints are dropped and recreated to include the new column so
the same indicator can be added independently to multiple repeat entries of the same section.
"""

from alembic import op
import sqlalchemy as sa


revision = 'add_dynamic_indicator_repeat_instance'
down_revision = 'add_validation_admin_permissions'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('dynamic_indicator_data', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('repeat_instance_number', sa.Integer(), nullable=True)
        )
        # Drop the old unique constraints that did NOT include repeat_instance_number
        batch_op.drop_constraint('_dynamic_indicator_entity_unique', type_='unique')
        batch_op.drop_constraint('_dynamic_indicator_public_unique', type_='unique')
        # Recreate them including repeat_instance_number (NULL is treated as a distinct value
        # by standard SQL, so two NULL rows are NOT considered duplicates; if you need to
        # prevent duplicate section-level indicators the application enforces it at the API level)
        batch_op.create_unique_constraint(
            '_dynamic_indicator_entity_unique',
            ['assignment_entity_status_id', 'section_id', 'indicator_bank_id', 'repeat_instance_number'],
        )
        batch_op.create_unique_constraint(
            '_dynamic_indicator_public_unique',
            ['public_submission_id', 'section_id', 'indicator_bank_id', 'repeat_instance_number'],
        )
        batch_op.create_index(
            'ix_dynamic_indicator_repeat_instance',
            ['section_id', 'repeat_instance_number'],
        )


def downgrade():
    with op.batch_alter_table('dynamic_indicator_data', schema=None) as batch_op:
        batch_op.drop_index('ix_dynamic_indicator_repeat_instance')
        batch_op.drop_constraint('_dynamic_indicator_entity_unique', type_='unique')
        batch_op.drop_constraint('_dynamic_indicator_public_unique', type_='unique')
        batch_op.create_unique_constraint(
            '_dynamic_indicator_entity_unique',
            ['assignment_entity_status_id', 'section_id', 'indicator_bank_id'],
        )
        batch_op.create_unique_constraint(
            '_dynamic_indicator_public_unique',
            ['public_submission_id', 'section_id', 'indicator_bank_id'],
        )
        batch_op.drop_column('repeat_instance_number')
