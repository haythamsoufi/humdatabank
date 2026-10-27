"""Allow multiple rejected/approved country access requests per user+country.

The previous UNIQUE (user_id, country_id, status) blocked rejecting a
re-request after an earlier rejection (second status='rejected' row).

Replace it with a partial unique index that only enforces one pending
request per user+country.

Revision ID: fix_car_pending_unique
Revises: fdrs_everyone_counts_snapshot
Create Date: 2026-10-27
"""
from alembic import op
import sqlalchemy as sa


revision = "fix_car_pending_unique"
down_revision = "fdrs_everyone_counts_snapshot"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint(
        "uq_user_country_status_active",
        "country_access_request",
        type_="unique",
    )
    op.create_index(
        "uq_car_user_country_pending",
        "country_access_request",
        ["user_id", "country_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
        sqlite_where=sa.text("status = 'pending'"),
    )


def downgrade():
    op.drop_index("uq_car_user_country_pending", table_name="country_access_request")
    op.create_unique_constraint(
        "uq_user_country_status_active",
        "country_access_request",
        ["user_id", "country_id", "status"],
    )
