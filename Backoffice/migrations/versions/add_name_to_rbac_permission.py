"""Add name to rbac_permission

Revision ID: add_name_to_rbac_permission
Revises: remove_legacy_user_role_and_flags
Create Date: 2026-01-19
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "add_name_to_rbac_permission"
down_revision = "remove_legacy_user_role_and_flags"
branch_labels = None
depends_on = None


def upgrade():
    # 1) Add column as nullable first (safe for existing rows)
    op.add_column("rbac_permission", sa.Column("name", sa.String(length=200), nullable=True))

    # 2) Backfill (best-effort):
    #    - Prefer existing description when available
    #    - Fall back to code
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            UPDATE rbac_permission
            SET name = description
            WHERE (name IS NULL OR name = '')
              AND description IS NOT NULL
              AND description <> ''
            """
        )
    )
    bind.execute(
        sa.text(
            """
            UPDATE rbac_permission
            SET name = code
            WHERE name IS NULL OR name = ''
            """
        )
    )

    # 3) Enforce NOT NULL (after backfill)
    op.alter_column(
        "rbac_permission",
        "name",
        existing_type=sa.String(length=200),
        nullable=False,
    )


def downgrade():
    op.drop_column("rbac_permission", "name")
