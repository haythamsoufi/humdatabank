"""Tag projects with a team category (NSD, …).

Revision ID: add_project_portfolio
Revises: ensure_core_project_table
Create Date: 2026-10-28

``portfolio`` is the owning team (NSD). ``fund`` stays the programme inside
that team (CBF, NSIA). Existing CBF/NSIA rows are backfilled as NSD.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "add_project_portfolio"
down_revision = "ensure_core_project_table"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = inspect(bind)
    if not insp.has_table("project"):
        return
    cols = {c["name"] for c in insp.get_columns("project")}
    if "portfolio" not in cols:
        op.add_column("project", sa.Column("portfolio", sa.String(length=40), nullable=True))
    indexes = {idx["name"] for idx in insp.get_indexes("project") if idx.get("name")}
    if "ix_project_portfolio" not in indexes:
        op.create_index("ix_project_portfolio", "project", ["portfolio"])
    op.execute(
        sa.text(
            "UPDATE project SET portfolio = 'NSD' "
            "WHERE (portfolio IS NULL OR portfolio = '') AND ("
            " upper(coalesce(fund, '')) IN ('CBF', 'NSIA') "
            " OR reference ILIKE 'CBF-%' "
            " OR reference ILIKE 'NSIA-%'"
            ")"
        )
    )


def downgrade():
    bind = op.get_bind()
    insp = inspect(bind)
    if not insp.has_table("project"):
        return
    indexes = {idx["name"] for idx in insp.get_indexes("project") if idx.get("name")}
    if "ix_project_portfolio" in indexes:
        op.drop_index("ix_project_portfolio", table_name="project")
    cols = {c["name"] for c in insp.get_columns("project")}
    if "portfolio" in cols:
        op.drop_column("project", "portfolio")
