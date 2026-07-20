"""Drop unused country.partof column

Legacy program-membership string never shown in the Backoffice UI and
superseded by NationalSociety.part_of. Remove from the country table and
public API country dimension.

Revision ID: drop_country_partof
Revises: add_missing_notification_types
Create Date: 2026-07-20
"""

from alembic import op
import sqlalchemy as sa


revision = 'drop_country_partof'
down_revision = 'add_missing_notification_types'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_column('country', 'partof')


def downgrade():
    op.add_column('country', sa.Column('partof', sa.String(length=100), nullable=True))
