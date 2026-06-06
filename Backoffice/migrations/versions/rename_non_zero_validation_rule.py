"""Rename non_zero validation rule to indicator_not_reported.

Revision ID: rename_non_zero_validation_rule
Revises: add_aes_reopened_after_close
Create Date: 2026-06-06
"""
from alembic import op
import sqlalchemy as sa


revision = "rename_non_zero_validation_rule"
down_revision = "add_aes_reopened_after_close"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            UPDATE validation_question_template
            SET question_code = 'indicator_not_reported',
                template_text = 'This indicator is not reported.'
            WHERE question_code = 'non_zero'
            """
        )
    )
    conn.execute(
        sa.text(
            """
            UPDATE validation_question
            SET rule_code = 'indicator_not_reported'
            WHERE rule_code = 'non_zero'
            """
        )
    )


def downgrade():
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            UPDATE validation_question_template
            SET question_code = 'non_zero',
                template_text = 'This indicator is reported as zero. Please confirm this is correct.'
            WHERE question_code = 'indicator_not_reported'
            """
        )
    )
    conn.execute(
        sa.text(
            """
            UPDATE validation_question
            SET rule_code = 'non_zero'
            WHERE rule_code = 'indicator_not_reported'
            """
        )
    )
