"""Turn on cross-assignment document reuse for FDRS document fields.

A multi-year file stored on an earlier FDRS assignment should satisfy the
same document field in later years. The entry form, completion, submit
check, validation tracker, and data-quality score all read
``config.cross_assignment_period_reuse``.

Revision ID: enable_fdrs_document_period_reuse
Revises: add_enable_offline_download
"""

from alembic import op


revision = "enable_fdrs_document_period_reuse"
down_revision = "add_enable_offline_download"
branch_labels = None
depends_on = None

# FDRS template. Document fields on that template are the four key documents
# plus any other document field published on the same form.
_FDRS_TEMPLATE_ID = 21


def upgrade():
    op.execute(
        f"""
        UPDATE form_item
        SET config = (
            COALESCE(config::jsonb, '{{}}'::jsonb)
            || '{{"cross_assignment_period_reuse": true}}'::jsonb
        )::json
        WHERE item_type = 'document_field'
          AND (
            template_id = {_FDRS_TEMPLATE_ID}
            OR section_id IN (
                SELECT id FROM form_section WHERE template_id = {_FDRS_TEMPLATE_ID}
            )
          )
        """
    )


def downgrade():
    op.execute(
        f"""
        UPDATE form_item
        SET config = (
            COALESCE(config::jsonb, '{{}}'::jsonb)
            || '{{"cross_assignment_period_reuse": false}}'::jsonb
        )::json
        WHERE item_type = 'document_field'
          AND (
            template_id = {_FDRS_TEMPLATE_ID}
            OR section_id IN (
                SELECT id FROM form_section WHERE template_id = {_FDRS_TEMPLATE_ID}
            )
          )
        """
    )
