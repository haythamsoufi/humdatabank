"""Add status to national_societies

Revision ID: add_ns_status
Revises: add_translation_catalog_version
Create Date: 2026-09-17
"""
from alembic import op
import sqlalchemy as sa


revision = "add_ns_status"
down_revision = "add_translation_catalog_version"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("national_societies", schema=None) as batch_op:
        batch_op.add_column(sa.Column("status", sa.String(length=50), nullable=True))

    op.execute(
        sa.text(
            "UPDATE national_societies "
            "SET status = CASE WHEN is_active THEN 'Active' ELSE 'Inactive' END "
            "WHERE status IS NULL"
        )
    )

    with op.batch_alter_table("national_societies", schema=None) as batch_op:
        batch_op.alter_column(
            "status",
            existing_type=sa.String(length=50),
            nullable=False,
            server_default="Active",
        )
        batch_op.create_index("ix_national_societies_status", ["status"], unique=False)


def downgrade():
    with op.batch_alter_table("national_societies", schema=None) as batch_op:
        batch_op.drop_index("ix_national_societies_status")
        batch_op.drop_column("status")
