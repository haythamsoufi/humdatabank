"""Add RBAC tables (roles, permissions, grants)

Revision ID: add_rbac_tables
Revises: add_pgvector_embeddings
Create Date: 2026-01-18
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "add_rbac_tables"
down_revision = "add_pgvector_embeddings"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "rbac_permission",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=150), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_rbac_permission_code"),
    )
    op.create_index("ix_rbac_permission_code", "rbac_permission", ["code"], unique=False)

    op.create_table(
        "rbac_role",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_rbac_role_code"),
    )
    op.create_index("ix_rbac_role_code", "rbac_role", ["code"], unique=False)

    op.create_table(
        "rbac_role_permission",
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.Column("permission_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["permission_id"], ["rbac_permission.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["role_id"], ["rbac_role.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("role_id", "permission_id"),
    )
    op.create_index("ix_rbac_role_permission_role", "rbac_role_permission", ["role_id"], unique=False)
    op.create_index("ix_rbac_role_permission_permission", "rbac_role_permission", ["permission_id"], unique=False)

    op.create_table(
        "rbac_user_role",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["role_id"], ["rbac_role.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "role_id"),
    )
    op.create_index("ix_rbac_user_role_user", "rbac_user_role", ["user_id"], unique=False)
    op.create_index("ix_rbac_user_role_role", "rbac_user_role", ["role_id"], unique=False)

    op.create_table(
        "rbac_access_grant",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("principal_type", sa.String(length=20), nullable=False),
        sa.Column("principal_id", sa.Integer(), nullable=False),
        sa.Column("permission_id", sa.Integer(), nullable=False),
        sa.Column("scope_kind", sa.String(length=20), nullable=False),
        sa.Column("entity_type", sa.String(length=50), nullable=True),
        sa.Column("entity_id", sa.Integer(), nullable=True),
        sa.Column("template_id", sa.Integer(), nullable=True),
        sa.Column("assigned_form_id", sa.Integer(), nullable=True),
        sa.Column("effect", sa.String(length=10), nullable=False, server_default="allow"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.CheckConstraint("principal_type IN ('user','role')", name="ck_rbac_access_grant_principal_type"),
        sa.CheckConstraint("scope_kind IN ('global','entity','template','assignment')", name="ck_rbac_access_grant_scope_kind"),
        sa.CheckConstraint("effect IN ('allow','deny')", name="ck_rbac_access_grant_effect"),
        sa.ForeignKeyConstraint(["assigned_form_id"], ["assigned_form.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["user.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["permission_id"], ["rbac_permission.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["template_id"], ["form_template.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "principal_type",
            "principal_id",
            "permission_id",
            "scope_kind",
            "entity_type",
            "entity_id",
            "template_id",
            "assigned_form_id",
            name="uq_rbac_access_grant_unique_target",
        ),
    )
    op.create_index(
        "ix_rbac_access_grant_principal",
        "rbac_access_grant",
        ["principal_type", "principal_id"],
        unique=False,
    )
    op.create_index("ix_rbac_access_grant_permission", "rbac_access_grant", ["permission_id"], unique=False)
    op.create_index("ix_rbac_access_grant_scope_template", "rbac_access_grant", ["scope_kind", "template_id"], unique=False)
    op.create_index("ix_rbac_access_grant_scope_assignment", "rbac_access_grant", ["scope_kind", "assigned_form_id"], unique=False)
    op.create_index("ix_rbac_access_grant_scope_entity", "rbac_access_grant", ["scope_kind", "entity_type", "entity_id"], unique=False)


def downgrade():
    op.drop_index("ix_rbac_access_grant_scope_entity", table_name="rbac_access_grant")
    op.drop_index("ix_rbac_access_grant_scope_assignment", table_name="rbac_access_grant")
    op.drop_index("ix_rbac_access_grant_scope_template", table_name="rbac_access_grant")
    op.drop_index("ix_rbac_access_grant_permission", table_name="rbac_access_grant")
    op.drop_index("ix_rbac_access_grant_principal", table_name="rbac_access_grant")
    op.drop_table("rbac_access_grant")

    op.drop_index("ix_rbac_user_role_role", table_name="rbac_user_role")
    op.drop_index("ix_rbac_user_role_user", table_name="rbac_user_role")
    op.drop_table("rbac_user_role")

    op.drop_index("ix_rbac_role_permission_permission", table_name="rbac_role_permission")
    op.drop_index("ix_rbac_role_permission_role", table_name="rbac_role_permission")
    op.drop_table("rbac_role_permission")

    op.drop_index("ix_rbac_role_code", table_name="rbac_role")
    op.drop_table("rbac_role")

    op.drop_index("ix_rbac_permission_code", table_name="rbac_permission")
    op.drop_table("rbac_permission")
