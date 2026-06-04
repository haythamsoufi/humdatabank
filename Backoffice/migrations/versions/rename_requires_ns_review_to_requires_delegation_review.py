"""Rename assigned_form.requires_ns_review to requires_delegation_review

Revision ID: rename_requires_delegation_review
Revises: add_sent_for_review_workflow
Create Date: 2026-06-03
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = 'rename_requires_delegation_review'
down_revision = 'add_sent_for_review_workflow'
branch_labels = None
depends_on = None


def _assigned_form_columns(bind):
    return {c['name'] for c in inspect(bind).get_columns('assigned_form')}


def upgrade():
    bind = op.get_bind()
    cols = _assigned_form_columns(bind)
    if 'requires_ns_review' in cols and 'requires_delegation_review' not in cols:
        op.alter_column(
            'assigned_form',
            'requires_ns_review',
            new_column_name='requires_delegation_review',
        )


def downgrade():
    bind = op.get_bind()
    cols = _assigned_form_columns(bind)
    if 'requires_delegation_review' in cols and 'requires_ns_review' not in cols:
        op.alter_column(
            'assigned_form',
            'requires_delegation_review',
            new_column_name='requires_ns_review',
        )
