"""Add archived_versions to submitted_document and submitted_document_countries M2M table.

Revision ID: 7c3e8f1a2b4d
Revises: b9ad7d386c90
Create Date: 2026-04-03
"""
from alembic import op
import sqlalchemy as sa

revision = '7c3e8f1a2b4d'
down_revision = 'b9ad7d386c90'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('submitted_document', sa.Column('archived_versions', sa.JSON(), nullable=True))

    op.create_table(
        'submitted_document_countries',
        sa.Column('submitted_document_id', sa.Integer(),
                  sa.ForeignKey('submitted_document.id', ondelete='CASCADE'),
                  primary_key=True),
        sa.Column('country_id', sa.Integer(),
                  sa.ForeignKey('country.id', ondelete='CASCADE'),
                  primary_key=True),
    )


def downgrade():
    op.drop_table('submitted_document_countries')
    op.drop_column('submitted_document', 'archived_versions')
