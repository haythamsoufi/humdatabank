"""Assignment access control: per-user assignment scope and per-assignment role restriction.

Revision ID: add_assignment_access_control
Revises: rename_upr_perm_visuals
Create Date: 2026-10-15

- ``user.assignment_access_mode``: ``all`` (default, unchanged behaviour) or ``selected``.
- ``user_assignment_access``: the assignments a ``selected`` user may reach.
- ``assigned_form_allowed_role``: RBAC roles allowed on an assignment. No rows means
  the assignment stays open to every user who otherwise has access.

Every existing user and assignment keeps full access: the mode defaults to ``all`` and
both link tables start empty.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "add_assignment_access_control"
down_revision = "rename_upr_perm_visuals"
branch_labels = None
depends_on = None


def _has_table(inspector, name: str) -> bool:
    return name in inspector.get_table_names()


def upgrade():
    conn = op.get_bind()
    inspector = inspect(conn)

    user_columns = {col["name"] for col in inspector.get_columns("user")}
    if "assignment_access_mode" not in user_columns:
        with op.batch_alter_table("user", schema=None) as batch_op:
            batch_op.add_column(
                sa.Column(
                    "assignment_access_mode",
                    sa.String(length=20),
                    nullable=False,
                    server_default="all",
                )
            )
    op.execute(
        "ALTER TABLE \"user\" DROP CONSTRAINT IF EXISTS ck_user_assignment_access_mode"
    )
    op.create_check_constraint(
        "ck_user_assignment_access_mode",
        "user",
        "assignment_access_mode IN ('all','selected')",
    )

    if not _has_table(inspector, "user_assignment_access"):
        op.create_table(
            "user_assignment_access",
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("assigned_form_id", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(
                ["assigned_form_id"], ["assigned_form.id"], ondelete="CASCADE"
            ),
            sa.PrimaryKeyConstraint("user_id", "assigned_form_id"),
        )
        op.create_index(
            "ix_user_assignment_access_user", "user_assignment_access", ["user_id"]
        )
        op.create_index(
            "ix_user_assignment_access_assignment",
            "user_assignment_access",
            ["assigned_form_id"],
        )

    if not _has_table(inspector, "assigned_form_allowed_role"):
        op.create_table(
            "assigned_form_allowed_role",
            sa.Column("assigned_form_id", sa.Integer(), nullable=False),
            sa.Column("role_id", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(
                ["assigned_form_id"], ["assigned_form.id"], ondelete="CASCADE"
            ),
            sa.ForeignKeyConstraint(["role_id"], ["rbac_role.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("assigned_form_id", "role_id"),
        )
        op.create_index(
            "ix_assigned_form_allowed_role_role",
            "assigned_form_allowed_role",
            ["role_id"],
        )


def downgrade():
    op.drop_index(
        "ix_assigned_form_allowed_role_role", table_name="assigned_form_allowed_role"
    )
    op.drop_table("assigned_form_allowed_role")
    op.drop_index(
        "ix_user_assignment_access_assignment", table_name="user_assignment_access"
    )
    op.drop_index("ix_user_assignment_access_user", table_name="user_assignment_access")
    op.drop_table("user_assignment_access")
    op.drop_constraint("ck_user_assignment_access_mode", "user", type_="check")
    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.drop_column("assignment_access_mode")
