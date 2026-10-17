"""Let a user's assignment scope cover every assignment of selected templates.

Revision ID: add_user_assignment_template_access
Revises: add_rbac_role_kind
Create Date: 2026-10-17

``user.assignment_access_mode`` gains ``templates`` alongside ``all`` and
``selected``. ``user_assignment_template_access`` stores the templates whose
current and future assignments that user may reach. Existing users stay on
``all`` with an empty link table.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "add_user_assignment_template_access"
down_revision = "add_rbac_role_kind"
branch_labels = None
depends_on = None


def _has_table(inspector, name: str) -> bool:
    return name in inspector.get_table_names()


def upgrade():
    conn = op.get_bind()
    inspector = inspect(conn)

    op.execute('ALTER TABLE "user" DROP CONSTRAINT IF EXISTS ck_user_assignment_access_mode')
    op.create_check_constraint(
        "ck_user_assignment_access_mode",
        "user",
        "assignment_access_mode IN ('all','selected','templates')",
    )

    if not _has_table(inspector, "user_assignment_template_access"):
        op.create_table(
            "user_assignment_template_access",
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("template_id", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(
                ["template_id"], ["form_template.id"], ondelete="CASCADE"
            ),
            sa.PrimaryKeyConstraint("user_id", "template_id"),
        )
        op.create_index(
            "ix_user_assignment_template_access_user",
            "user_assignment_template_access",
            ["user_id"],
        )
        op.create_index(
            "ix_user_assignment_template_access_template",
            "user_assignment_template_access",
            ["template_id"],
        )


def downgrade():
    op.execute(
        "UPDATE \"user\" SET assignment_access_mode = 'all' "
        "WHERE assignment_access_mode = 'templates'"
    )
    op.execute('ALTER TABLE "user" DROP CONSTRAINT IF EXISTS ck_user_assignment_access_mode')
    op.create_check_constraint(
        "ck_user_assignment_access_mode",
        "user",
        "assignment_access_mode IN ('all','selected')",
    )
    inspector = inspect(op.get_bind())
    if "user_assignment_template_access" in inspector.get_table_names():
        op.drop_index(
            "ix_user_assignment_template_access_template",
            table_name="user_assignment_template_access",
        )
        op.drop_index(
            "ix_user_assignment_template_access_user",
            table_name="user_assignment_template_access",
        )
        op.drop_table("user_assignment_template_access")
