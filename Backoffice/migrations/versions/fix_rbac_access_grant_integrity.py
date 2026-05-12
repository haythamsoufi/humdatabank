"""Fix RBAC access grant integrity (scope validation + true uniqueness)

Problem:
- The previous UNIQUE constraint on rbac_access_grant included nullable scope columns.
  In PostgreSQL, UNIQUE constraints allow multiple rows when any key column is NULL,
  so duplicate (and even conflicting allow/deny) grants could be inserted.
- Scope payload columns were not enforced consistently (e.g., global grants with template_id set).

This migration:
- Normalizes / deletes invalid scope rows (best-effort).
- De-duplicates grants deterministically (deny preferred; otherwise newest).
- Replaces the broken UNIQUE constraint with partial unique indexes per scope_kind.
- Adds a check constraint to enforce valid scope payload shape.

Revision ID: fix_rbac_access_grant_integrity
Revises: add_name_to_rbac_permission
Create Date: 2026-01-19
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "fix_rbac_access_grant_integrity"
down_revision = "add_name_to_rbac_permission"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()

    # ---------------------------------------------------------------------
    # 1) Normalize scope payloads (best-effort)
    # ---------------------------------------------------------------------
    # Global: no scope payload columns
    bind.execute(
        sa.text(
            """
            UPDATE rbac_access_grant
            SET entity_type = NULL,
                entity_id = NULL,
                template_id = NULL,
                assigned_form_id = NULL
            WHERE scope_kind = 'global'
              AND (
                entity_type IS NOT NULL OR entity_id IS NOT NULL OR
                template_id IS NOT NULL OR assigned_form_id IS NOT NULL
              )
            """
        )
    )

    # Entity: entity_type/entity_id required; other scope columns must be NULL
    bind.execute(
        sa.text(
            """
            UPDATE rbac_access_grant
            SET template_id = NULL,
                assigned_form_id = NULL
            WHERE scope_kind = 'entity'
              AND (template_id IS NOT NULL OR assigned_form_id IS NOT NULL)
            """
        )
    )

    # Template: template_id required; other scope columns must be NULL
    bind.execute(
        sa.text(
            """
            UPDATE rbac_access_grant
            SET entity_type = NULL,
                entity_id = NULL,
                assigned_form_id = NULL
            WHERE scope_kind = 'template'
              AND (entity_type IS NOT NULL OR entity_id IS NOT NULL OR assigned_form_id IS NOT NULL)
            """
        )
    )

    # Assignment: assigned_form_id required; other scope columns must be NULL
    bind.execute(
        sa.text(
            """
            UPDATE rbac_access_grant
            SET entity_type = NULL,
                entity_id = NULL,
                template_id = NULL
            WHERE scope_kind = 'assignment'
              AND (entity_type IS NOT NULL OR entity_id IS NOT NULL OR template_id IS NOT NULL)
            """
        )
    )

    # Ensure effect is present (defensive)
    bind.execute(
        sa.text(
            """
            UPDATE rbac_access_grant
            SET effect = 'allow'
            WHERE effect IS NULL OR effect = ''
            """
        )
    )

    # Delete rows that cannot be made valid (missing required scope payload)
    bind.execute(
        sa.text(
            """
            DELETE FROM rbac_access_grant
            WHERE
              (scope_kind = 'entity' AND (entity_type IS NULL OR entity_type = '' OR entity_id IS NULL))
              OR (scope_kind = 'template' AND template_id IS NULL)
              OR (scope_kind = 'assignment' AND assigned_form_id IS NULL)
            """
        )
    )

    # ---------------------------------------------------------------------
    # 2) De-duplicate grants (deny preferred; otherwise newest)
    # ---------------------------------------------------------------------
    # Partition keys depend on scope_kind; use a single partition that includes
    # all payload columns (NULL-safe via COALESCE) to match intended uniqueness.
    bind.execute(
        sa.text(
            """
            DELETE FROM rbac_access_grant g
            USING (
              SELECT
                id,
                ROW_NUMBER() OVER (
                  PARTITION BY
                    principal_type,
                    principal_id,
                    permission_id,
                    scope_kind,
                    COALESCE(entity_type, ''),
                    COALESCE(entity_id, 0),
                    COALESCE(template_id, 0),
                    COALESCE(assigned_form_id, 0)
                  ORDER BY
                    CASE WHEN effect = 'deny' THEN 1 ELSE 0 END DESC,
                    created_at DESC NULLS LAST,
                    id DESC
                ) AS rn
              FROM rbac_access_grant
            ) d
            WHERE g.id = d.id
              AND d.rn > 1
            """
        )
    )

    # ---------------------------------------------------------------------
    # 3) Replace broken UNIQUE constraint with real per-scope uniqueness
    # ---------------------------------------------------------------------
    # Old constraint name from add_rbac_tables.py
    with op.batch_alter_table("rbac_access_grant") as batch_op:
        batch_op.drop_constraint("uq_rbac_access_grant_unique_target", type_="unique")

    # Enforce valid scope payload shape
    op.create_check_constraint(
        "ck_rbac_access_grant_scope_payload",
        "rbac_access_grant",
        """
        (
          (scope_kind = 'global'
            AND entity_type IS NULL AND entity_id IS NULL AND template_id IS NULL AND assigned_form_id IS NULL)
          OR
          (scope_kind = 'entity'
            AND entity_type IS NOT NULL AND entity_type <> '' AND entity_id IS NOT NULL
            AND template_id IS NULL AND assigned_form_id IS NULL)
          OR
          (scope_kind = 'template'
            AND template_id IS NOT NULL
            AND entity_type IS NULL AND entity_id IS NULL AND assigned_form_id IS NULL)
          OR
          (scope_kind = 'assignment'
            AND assigned_form_id IS NOT NULL
            AND entity_type IS NULL AND entity_id IS NULL AND template_id IS NULL)
        )
        """,
    )

    # True uniqueness using partial unique indexes per scope_kind
    op.create_index(
        "uq_rbac_access_grant_global",
        "rbac_access_grant",
        ["principal_type", "principal_id", "permission_id"],
        unique=True,
        postgresql_where=sa.text("scope_kind = 'global'"),
    )
    op.create_index(
        "uq_rbac_access_grant_entity",
        "rbac_access_grant",
        ["principal_type", "principal_id", "permission_id", "entity_type", "entity_id"],
        unique=True,
        postgresql_where=sa.text("scope_kind = 'entity'"),
    )
    op.create_index(
        "uq_rbac_access_grant_template",
        "rbac_access_grant",
        ["principal_type", "principal_id", "permission_id", "template_id"],
        unique=True,
        postgresql_where=sa.text("scope_kind = 'template'"),
    )
    op.create_index(
        "uq_rbac_access_grant_assignment",
        "rbac_access_grant",
        ["principal_type", "principal_id", "permission_id", "assigned_form_id"],
        unique=True,
        postgresql_where=sa.text("scope_kind = 'assignment'"),
    )


def downgrade():
    # Drop partial unique indexes and scope payload constraint, restore old UNIQUE (best-effort).
    op.drop_index("uq_rbac_access_grant_assignment", table_name="rbac_access_grant")
    op.drop_index("uq_rbac_access_grant_template", table_name="rbac_access_grant")
    op.drop_index("uq_rbac_access_grant_entity", table_name="rbac_access_grant")
    op.drop_index("uq_rbac_access_grant_global", table_name="rbac_access_grant")

    op.drop_constraint("ck_rbac_access_grant_scope_payload", "rbac_access_grant", type_="check")

    with op.batch_alter_table("rbac_access_grant") as batch_op:
        batch_op.create_unique_constraint(
            "uq_rbac_access_grant_unique_target",
            [
                "principal_type",
                "principal_id",
                "permission_id",
                "scope_kind",
                "entity_type",
                "entity_id",
                "template_id",
                "assigned_form_id",
            ],
        )
