"""add translation fields for organization entities

Revision ID: add_org_translation_fields
Revises: add_entity_based_campaigns
Create Date: 2025-12-24 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = 'add_org_translation_fields'
down_revision = 'add_entity_based_campaigns'
branch_labels = None
depends_on = None


TABLES_WITH_TRANSLATIONS = [
    'ns_branches',
    'ns_subbranches',
    'ns_localunits',
    'secretariat_divisions',
    'secretariat_departments',
    'secretariat_regional_offices',
    'secretariat_cluster_offices',
]


def upgrade():
    jsonb_type = postgresql.JSONB(astext_type=sa.Text())
    for table in TABLES_WITH_TRANSLATIONS:
        op.add_column(
            table,
            sa.Column('name_translations', jsonb_type, nullable=True)
        )
        op.execute(
            f"UPDATE {table} SET name_translations = '{{}}'::jsonb "
            "WHERE name_translations IS NULL"
        )


def downgrade():
    for table in TABLES_WITH_TRANSLATIONS:
        op.drop_column(table, 'name_translations')
