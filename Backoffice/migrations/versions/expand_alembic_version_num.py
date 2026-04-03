"""Expand alembic_version.version_num length

This repo uses descriptive revision ids (sometimes > 32 chars). Some databases
were initialized with Alembic's default `alembic_version.version_num VARCHAR(32)`,
which breaks upgrades when the next revision id exceeds 32 characters.

Revision ID: expand_alembic_version_num
Revises: remove_template_type
Create Date: 2026-01-19
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "expand_alembic_version_num"
down_revision = "remove_template_type"
branch_labels = None
depends_on = None


def upgrade():
    # Postgres: widening varchar is safe and fast.
    op.execute(sa.text("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(64)"))


def downgrade():
    # Best-effort downgrade: only shrink if current value fits.
    bind = op.get_bind()
    max_len = bind.execute(sa.text("SELECT MAX(LENGTH(version_num)) FROM alembic_version")).scalar()
    if max_len and int(max_len) > 32:
        raise RuntimeError(
            f"Cannot downgrade: alembic_version.version_num contains values longer than 32 (max length: {max_len})."
        )
    op.execute(sa.text("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(32)"))
