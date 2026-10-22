"""Save the Everyone Counts calculation so the explorer tab does not rebuild it.

Revision ID: fdrs_everyone_counts_snapshot
Revises: fdrs_volunteer_deaths_kpi
Create Date: 2026-10-22

Opening Everyone Counts ran the FDRS panel query and the chapter build inside
the request. Production closes that request (statement timeout, then the
gateway) before the page can answer. The tab now reads this row. Refresh
rebuilds it in the background.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "fdrs_everyone_counts_snapshot"
down_revision = "fdrs_volunteer_deaths_kpi"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "fdrs_everyone_counts_snapshot",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("template_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("build_token", sa.String(length=64), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("built_at", sa.DateTime(), nullable=True),
        sa.Column("built_by_user_id", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["built_by_user_id"], ["user.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("template_id", name="uq_fdrs_everyone_counts_snapshot_template"),
    )


def downgrade():
    op.drop_table("fdrs_everyone_counts_snapshot")
