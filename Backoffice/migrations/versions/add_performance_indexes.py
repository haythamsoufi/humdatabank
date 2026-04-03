"""Add performance indexes for query optimization

Revision ID: add_performance_indexes
Revises: add_quiz_score_to_user
Create Date: 2024-01-01 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_performance_indexes'
down_revision = 'add_can_explore_data'  # Update this to match latest migration
branch_labels = None
depends_on = None


def upgrade():
    # Index for FormData queries (frequently filtered by assignment and form_item)
    op.create_index(
        'idx_formdata_assignment_formitem',
        'form_data',
        ['assignment_entity_status_id', 'form_item_id'],
        unique=False
    )

    # Index for FormItem queries (ordered by section and order)
    op.create_index(
        'idx_formitem_section_order',
        'form_item',
        ['section_id', 'order'],
        unique=False
    )

    # Index for RepeatGroupData queries (filtered by instance)
    op.create_index(
        'idx_repeatgroupdata_instance',
        'repeat_group_data',
        ['repeat_instance_id'],
        unique=False
    )

    # Index for DynamicIndicatorData queries (filtered by assignment status)
    op.create_index(
        'idx_dynamicindicator_data_status',
        'dynamic_indicator_data',
        ['assignment_entity_status_id'],
        unique=False
    )

    # Index for UserEntityPermission queries (frequently filtered by user and type)
    op.create_index(
        'idx_user_entity_permission_user_type',
        'user_entity_permissions',
        ['user_id', 'entity_type'],
        unique=False
    )


def downgrade():
    op.drop_index('idx_user_entity_permission_user_type', table_name='user_entity_permissions')
    op.drop_index('idx_dynamicindicator_data_status', table_name='dynamic_indicator_data')
    op.drop_index('idx_repeatgroupdata_instance', table_name='repeat_group_data')
    op.drop_index('idx_formitem_section_order', table_name='form_item')
    op.drop_index('idx_formdata_assignment_formitem', table_name='form_data')
