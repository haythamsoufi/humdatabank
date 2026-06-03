"""Add integrity constraints for form submission data tables (F1, F2, F3)

Revision ID: add_data_submission_integrity
Revises: add_api_key_audit_usage_link
Create Date: 2026-06-02

Adds:
- CHECK constraints ensuring at least one parent FK is set (form_data, dynamic_indicator_data, repeat_group_instance)
- Partial UNIQUE indexes on form_data (aes + item, public + item)
- UNIQUE index on repeat_group_data (instance + item)
"""

from alembic import op


revision = 'add_data_submission_integrity'
down_revision = 'add_api_key_audit_usage_link'
branch_labels = None
depends_on = None


def upgrade():
    op.create_check_constraint(
        'ck_form_data_parent',
        'form_data',
        '(assignment_entity_status_id IS NOT NULL) OR (public_submission_id IS NOT NULL)',
    )
    op.create_check_constraint(
        'ck_dynamic_indicator_data_parent',
        'dynamic_indicator_data',
        '(assignment_entity_status_id IS NOT NULL) OR (public_submission_id IS NOT NULL)',
    )
    op.create_check_constraint(
        'ck_repeat_group_instance_parent',
        'repeat_group_instance',
        '(assignment_entity_status_id IS NOT NULL) OR (public_submission_id IS NOT NULL)',
    )

    op.execute(
        """
        CREATE UNIQUE INDEX uq_form_data_aes_item
        ON form_data (assignment_entity_status_id, form_item_id)
        WHERE assignment_entity_status_id IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_form_data_public_item
        ON form_data (public_submission_id, form_item_id)
        WHERE public_submission_id IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_repeat_group_data_instance_item
        ON repeat_group_data (repeat_instance_id, form_item_id)
        """
    )


def downgrade():
    op.execute('DROP INDEX IF EXISTS uq_repeat_group_data_instance_item')
    op.execute('DROP INDEX IF EXISTS uq_form_data_public_item')
    op.execute('DROP INDEX IF EXISTS uq_form_data_aes_item')

    op.drop_constraint('ck_repeat_group_instance_parent', 'repeat_group_instance', type_='check')
    op.drop_constraint('ck_dynamic_indicator_data_parent', 'dynamic_indicator_data', type_='check')
    op.drop_constraint('ck_form_data_parent', 'form_data', type_='check')
