"""Rename year column to period in submitted_document table

Revision ID: rename_year_to_period
Revises: add_performance_indexes
Create Date: 2025-01-22 12:00:00.000000

This migration renames the 'year' column to 'period' and changes its type
from Integer to String to support different period formats (single year, year range, month range).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = 'rename_year_to_period'
down_revision = 'remove_legacy_lang_cols'
branch_labels = None
depends_on = None


def upgrade():
    # Drop the existing index on year column
    op.drop_index('ix_submitted_doc_year', table_name='submitted_document')

    # Change the type to String using a cast
    op.alter_column(
        'submitted_document',
        'year',
        type_=sa.String(length=100),
        existing_type=sa.Integer(),
        existing_nullable=True,
        postgresql_using='year::text'
    )

    # Rename the column from year to period
    op.alter_column(
        'submitted_document',
        'year',
        new_column_name='period',
        existing_type=sa.String(length=100),
        existing_nullable=True
    )

    # Create new index on period column
    op.create_index('ix_submitted_doc_period', 'submitted_document', ['period'])


def downgrade():
    # Drop the index on period column
    op.drop_index('ix_submitted_doc_period', table_name='submitted_document')

    # Rename the column back from period to year
    op.alter_column(
        'submitted_document',
        'period',
        new_column_name='year',
        existing_type=sa.String(length=100),
        existing_nullable=True
    )

    # Change the type back to Integer using a safe cast
    op.alter_column(
        'submitted_document',
        'year',
        type_=sa.Integer(),
        existing_type=sa.String(length=100),
        existing_nullable=True,
        postgresql_using="CASE WHEN year ~ '^[0-9]{4}$' THEN year::integer ELSE NULL END"
    )

    # Recreate the index on year column
    op.create_index('ix_submitted_doc_year', 'submitted_document', ['year'])
