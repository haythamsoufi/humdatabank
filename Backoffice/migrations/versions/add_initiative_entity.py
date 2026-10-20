"""Add the initiative entity type table for funded investments (NSD NSIA / CBF).

Revision ID: add_initiative_entity
Revises: add_resource_external_url
Create Date: 2026-10-20

An initiative is a funded investment that reports on its own schedule. It becomes
an assignable entity (AssignmentEntityStatus.entity_type = 'initiative'), so its
reports reuse the form builder, assignment workflow and dashboard cards. The
entity_type columns are String(50) with no CHECK constraint, so no enum change is
needed in the database.
"""

from alembic import op
import sqlalchemy as sa


revision = "add_initiative_entity"
down_revision = "add_resource_external_url"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "initiative",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("reference", sa.String(length=50), nullable=False, unique=True),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column(
            "national_society_id",
            sa.Integer(),
            sa.ForeignKey("national_societies.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_initiative_national_society_id", "initiative", ["national_society_id"])


def downgrade():
    op.drop_index("ix_initiative_national_society_id", table_name="initiative")
    op.drop_table("initiative")
