"""Add resource_subcategory table and FK on resource

Revision ID: add_resource_subcategories
Revises: add_user_session_id_activity_log
Create Date: 2026-04-16

"""
from alembic import op
import sqlalchemy as sa


revision = "add_resource_subcategories"
down_revision = "add_user_session_id_activity_log"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "resource_subcategory",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_resource_subcategory_display_order",
        "resource_subcategory",
        ["display_order"],
    )
    op.add_column(
        "resource",
        sa.Column("resource_subcategory_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_resource_resource_subcategory",
        "resource",
        "resource_subcategory",
        ["resource_subcategory_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_resource_subcategory_id",
        "resource",
        ["resource_subcategory_id"],
    )


def downgrade():
    op.drop_index("ix_resource_subcategory_id", table_name="resource")
    op.drop_constraint("fk_resource_resource_subcategory", "resource", type_="foreignkey")
    op.drop_column("resource", "resource_subcategory_id")
    op.drop_index("ix_resource_subcategory_display_order", table_name="resource_subcategory")
    op.drop_table("resource_subcategory")
