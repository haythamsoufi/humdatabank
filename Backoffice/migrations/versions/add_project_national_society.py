"""Link a project to the National Society that implements it.

Revision ID: add_project_national_society
Revises: drop_report_builder
Create Date: 2026-11-18

Projects in the portfolio then stored as ``US Macro Awards`` (renamed to
Global Awards by ``rename_global_awards``, which runs after this revision)
kept the country name in ``organization_name``. Where the country has one
National Society, point the project at that society and keep its official name.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "add_project_national_society"
down_revision = "drop_report_builder"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = inspect(bind)
    if not insp.has_table("project") or not insp.has_table("national_societies"):
        return
    cols = {c["name"] for c in insp.get_columns("project")}
    if "national_society_id" not in cols:
        op.add_column("project", sa.Column("national_society_id", sa.Integer(), nullable=True))
        op.create_foreign_key(
            "fk_project_national_society_id",
            "project",
            "national_societies",
            ["national_society_id"],
            ["id"],
            ondelete="SET NULL",
        )
    indexes = {idx["name"] for idx in insp.get_indexes("project") if idx.get("name")}
    if "ix_project_national_society" not in indexes:
        op.create_index("ix_project_national_society", "project", ["national_society_id"])
    op.execute(
        sa.text(
            """
            UPDATE project AS p
            SET national_society_id = ns.id,
                organization_name = ns.name
            FROM national_societies AS ns
            WHERE p.portfolio = 'US Macro Awards'
              AND p.national_society_id IS NULL
              AND ns.country_id = p.country_id
              AND (
                SELECT COUNT(*)
                FROM national_societies AS n2
                WHERE n2.country_id = p.country_id
                  AND n2.is_active IS TRUE
              ) = 1
              AND ns.is_active IS TRUE
            """
        )
    )


def downgrade():
    bind = op.get_bind()
    insp = inspect(bind)
    if not insp.has_table("project"):
        return
    indexes = {idx["name"] for idx in insp.get_indexes("project") if idx.get("name")}
    if "ix_project_national_society" in indexes:
        op.drop_index("ix_project_national_society", table_name="project")
    fks = {fk["name"] for fk in insp.get_foreign_keys("project") if fk.get("name")}
    if "fk_project_national_society_id" in fks:
        op.drop_constraint("fk_project_national_society_id", "project", type_="foreignkey")
    cols = {c["name"] for c in insp.get_columns("project")}
    if "national_society_id" in cols:
        op.drop_column("project", "national_society_id")
