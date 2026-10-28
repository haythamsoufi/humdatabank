"""Normalize AES entity_type to core 'project'.

Revision ID: aes_entity_type_project
Revises: add_nsd_project_table
Create Date: 2026-10-28

No-op on prod when no rows used the draft ``nsd_project`` entity_type.
Uses a set-based UPDATE so it is safe to re-run and cannot fail on empty tables.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "aes_entity_type_project"
down_revision = "add_nsd_project_table"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if not inspect(bind).has_table("assignment_entity_status"):
        return

    # Unique key is (assigned_form_id, entity_type, entity_id). Renaming the
    # type string alone cannot collide unless both values already exist for the
    # same pair — which never happens when the draft type was never shipped.
    op.execute(
        sa.text(
            "UPDATE assignment_entity_status SET entity_type = 'project' "
            "WHERE entity_type = 'nsd_project'"
        )
    )


def downgrade():
    # Do not rewrite project → nsd_project; core owns the type now.
    pass
