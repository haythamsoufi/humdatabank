"""Add translation_catalog_version

Revision ID: add_translation_catalog_version
Revises: add_aes_status_changed_by
Create Date: 2026-09-16

Single-row counter bumped on every catalog write. Workers poll it to notice a
peer's translation edit now that .po/.mo artifacts are materialized per
container instead of shared on persistent storage.
"""
from alembic import op
import sqlalchemy as sa


revision = 'add_translation_catalog_version'
down_revision = 'add_aes_status_changed_by'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'translation_catalog_version',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('version', sa.BigInteger(), nullable=False, server_default='1'),
        sa.Column(
            'updated_at',
            sa.DateTime(),
            nullable=False,
            server_default=sa.text('CURRENT_TIMESTAMP'),
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    # Seed the row so readers never have to distinguish "missing" from "never changed".
    op.execute(
        "INSERT INTO translation_catalog_version (id, version) VALUES (1, 1) "
        "ON CONFLICT (id) DO NOTHING"
    )


def downgrade():
    op.drop_table('translation_catalog_version')
