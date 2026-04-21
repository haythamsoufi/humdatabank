"""Add linked_entity_type and linked_entity_id to submitted_document.

Revision ID: 8e2a9c1f4b0d
Revises: 7c3e8f1a2b4d
Create Date: 2026-04-03
"""
from alembic import op
import sqlalchemy as sa


revision = '8e2a9c1f4b0d'
down_revision = '7c3e8f1a2b4d'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'submitted_document',
        sa.Column('linked_entity_type', sa.String(length=50), nullable=True),
    )
    op.add_column(
        'submitted_document',
        sa.Column('linked_entity_id', sa.Integer(), nullable=True),
    )
    op.create_index(
        'ix_submitted_doc_linked_entity',
        'submitted_document',
        ['linked_entity_type', 'linked_entity_id'],
    )
    # Backfill from country_id for existing standalone-style rows
    op.execute(
        """
        UPDATE submitted_document
        SET linked_entity_type = 'country', linked_entity_id = country_id
        WHERE country_id IS NOT NULL
          AND (linked_entity_type IS NULL OR linked_entity_id IS NULL)
        """
    )


def downgrade():
    op.drop_index('ix_submitted_doc_linked_entity', table_name='submitted_document')
    op.drop_column('submitted_document', 'linked_entity_id')
    op.drop_column('submitted_document', 'linked_entity_type')
