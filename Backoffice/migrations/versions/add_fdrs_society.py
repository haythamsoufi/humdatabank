"""FDRS society reference (DON code, zone, coordinates) for the public-frontend adapter.

Revision ID: add_fdrs_society
Revises: add_assignment_access_control
Create Date: 2026-10-16

``fdrs_society`` maps the legacy FDRS DON code (``DKEN001``) and zone (``S1``-``S5``)
to a ``country`` row. The table starts empty; seed it with
``flask fdrs-societies import``.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "add_fdrs_society"
down_revision = "add_assignment_access_control"
branch_labels = None
depends_on = None


def upgrade():
    inspector = inspect(op.get_bind())
    if "fdrs_society" in inspector.get_table_names():
        return
    op.create_table(
        "fdrs_society",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("don_code", sa.String(length=20), nullable=False),
        sa.Column("country_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("country_name", sa.String(length=255), nullable=True),
        sa.Column("iso2", sa.String(length=2), nullable=True),
        sa.Column("iso3", sa.String(length=3), nullable=True),
        sa.Column("zone_code", sa.String(length=2), nullable=True),
        sa.Column("zone_name", sa.String(length=100), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("admission_date", sa.Date(), nullable=True),
        sa.Column("admission_date_note", sa.Text(), nullable=True),
        sa.Column("currency_code", sa.String(length=3), nullable=True),
        sa.Column("search_string", sa.Text(), nullable=True),
        sa.Column("website", sa.Text(), nullable=True),
        sa.Column("facebook", sa.Text(), nullable=True),
        sa.Column("twitter", sa.Text(), nullable=True),
        sa.Column("other_social", sa.Text(), nullable=True),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["country_id"], ["country.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_fdrs_society_don_code", "fdrs_society", ["don_code"], unique=True)
    op.create_index("ix_fdrs_society_country_id", "fdrs_society", ["country_id"])
    op.create_index("ix_fdrs_society_zone_code", "fdrs_society", ["zone_code"])


def downgrade():
    op.drop_index("ix_fdrs_society_zone_code", table_name="fdrs_society")
    op.drop_index("ix_fdrs_society_country_id", table_name="fdrs_society")
    op.drop_index("ix_fdrs_society_don_code", table_name="fdrs_society")
    op.drop_table("fdrs_society")
