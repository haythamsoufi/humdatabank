"""Add AssignedForm.scope and project_id for per-project report cycles.

Revision ID: add_assigned_form_scope_project
Revises: add_ifrc_decision_support
Create Date: 2026-11-06

``scope=campaign`` (default) is the classic multi-entity round.
``scope=project_cycle`` is one project report, owned via ``project_id``.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "add_assigned_form_scope_project"
down_revision = "add_ifrc_decision_support"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = inspect(bind)
    if not insp.has_table("assigned_form"):
        return
    cols = {c["name"] for c in insp.get_columns("assigned_form")}
    if "scope" not in cols:
        op.add_column(
            "assigned_form",
            sa.Column(
                "scope",
                sa.String(length=20),
                nullable=False,
                server_default="campaign",
            ),
        )
    if "project_id" not in cols:
        op.add_column(
            "assigned_form",
            sa.Column("project_id", sa.Integer(), nullable=True),
        )
        if insp.has_table("project"):
            op.create_foreign_key(
                "fk_assigned_form_project_id",
                "assigned_form",
                "project",
                ["project_id"],
                ["id"],
                ondelete="CASCADE",
            )
    indexes = {idx["name"] for idx in insp.get_indexes("assigned_form") if idx.get("name")}
    if "ix_assigned_form_scope" not in indexes:
        op.create_index("ix_assigned_form_scope", "assigned_form", ["scope"])
    if "ix_assigned_form_project" not in indexes:
        op.create_index("ix_assigned_form_project", "assigned_form", ["project_id"])


def downgrade():
    bind = op.get_bind()
    insp = inspect(bind)
    if not insp.has_table("assigned_form"):
        return
    indexes = {idx["name"] for idx in insp.get_indexes("assigned_form") if idx.get("name")}
    if "ix_assigned_form_project" in indexes:
        op.drop_index("ix_assigned_form_project", table_name="assigned_form")
    if "ix_assigned_form_scope" in indexes:
        op.drop_index("ix_assigned_form_scope", table_name="assigned_form")
    fks = {fk.get("name") for fk in insp.get_foreign_keys("assigned_form") if fk.get("name")}
    if "fk_assigned_form_project_id" in fks:
        op.drop_constraint("fk_assigned_form_project_id", "assigned_form", type_="foreignkey")
    cols = {c["name"] for c in insp.get_columns("assigned_form")}
    if "project_id" in cols:
        op.drop_column("assigned_form", "project_id")
    if "scope" in cols:
        op.drop_column("assigned_form", "scope")
