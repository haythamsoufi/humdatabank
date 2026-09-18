"""Rename upr_visuals RBAC codes and plugin_data rows to upr.

Revision ID: rename_upr_visuals_rbac
Revises: add_page_submission
Create Date: 2026-09-18
"""

from alembic import op
from sqlalchemy import text

revision = "rename_upr_visuals_rbac"
down_revision = "add_page_submission"
branch_labels = None
depends_on = None

_OLD_PERMISSION = "admin.data_explore.upr_visuals"
_NEW_PERMISSION = "admin.data_explore.upr"
_OLD_ROLE = "admin_data_explorer_upr_visuals"
_NEW_ROLE = "admin_data_explorer_upr"
_PERMISSION_NAME = "Data Explorer: UPR"
_PERMISSION_DESCRIPTION = "Access Unified Plan and Report visuals in Data Explorer"
_ROLE_NAME = "Admin: Data Explorer (UPR)"
_ROLE_DESCRIPTION = "Access Unified Plan and Report visuals in Data Explorer."


def _rename_permission(conn) -> None:
    old = conn.execute(
        text("SELECT id FROM rbac_permission WHERE code = :code"),
        {"code": _OLD_PERMISSION},
    ).fetchone()
    if not old:
        return
    new = conn.execute(
        text("SELECT id FROM rbac_permission WHERE code = :code"),
        {"code": _NEW_PERMISSION},
    ).fetchone()
    if new:
        conn.execute(
            text("UPDATE rbac_role_permission SET permission_id = :new_id WHERE permission_id = :old_id"),
            {"new_id": new[0], "old_id": old[0]},
        )
        conn.execute(text("DELETE FROM rbac_permission WHERE id = :perm_id"), {"perm_id": old[0]})
        return
    conn.execute(
        text(
            """
            UPDATE rbac_permission
            SET code = :new_code, name = :name, description = :description
            WHERE code = :old_code
            """
        ),
        {
            "old_code": _OLD_PERMISSION,
            "new_code": _NEW_PERMISSION,
            "name": _PERMISSION_NAME,
            "description": _PERMISSION_DESCRIPTION,
        },
    )


def _rename_role(conn) -> None:
    old = conn.execute(
        text("SELECT id FROM rbac_role WHERE code = :code"),
        {"code": _OLD_ROLE},
    ).fetchone()
    if not old:
        return
    new = conn.execute(
        text("SELECT id FROM rbac_role WHERE code = :code"),
        {"code": _NEW_ROLE},
    ).fetchone()
    if new:
        conn.execute(
            text(
                """
                INSERT INTO rbac_user_role (user_id, role_id, created_at)
                SELECT user_id, :new_role_id, created_at
                FROM rbac_user_role
                WHERE role_id = :old_role_id
                ON CONFLICT DO NOTHING
                """
            ),
            {"old_role_id": old[0], "new_role_id": new[0]},
        )
        conn.execute(text("DELETE FROM rbac_user_role WHERE role_id = :role_id"), {"role_id": old[0]})
        conn.execute(text("DELETE FROM rbac_role_permission WHERE role_id = :role_id"), {"role_id": old[0]})
        conn.execute(text("DELETE FROM rbac_role WHERE id = :role_id"), {"role_id": old[0]})
        return
    conn.execute(
        text(
            """
            UPDATE rbac_role
            SET code = :new_code, name = :name, description = :description
            WHERE code = :old_code
            """
        ),
        {
            "old_code": _OLD_ROLE,
            "new_code": _NEW_ROLE,
            "name": _ROLE_NAME,
            "description": _ROLE_DESCRIPTION,
        },
    )


def upgrade():
    conn = op.get_bind()
    _rename_permission(conn)
    _rename_role(conn)
    conn.execute(
        text("UPDATE plugin_data SET plugin_id = 'upr' WHERE plugin_id = 'upr_visuals'")
    )


def downgrade():
    conn = op.get_bind()
    conn.execute(
        text("UPDATE plugin_data SET plugin_id = 'upr_visuals' WHERE plugin_id = 'upr'")
    )
    new_perm = conn.execute(
        text("SELECT id FROM rbac_permission WHERE code = :code"),
        {"code": _NEW_PERMISSION},
    ).fetchone()
    old_perm = conn.execute(
        text("SELECT id FROM rbac_permission WHERE code = :code"),
        {"code": _OLD_PERMISSION},
    ).fetchone()
    if new_perm and not old_perm:
        conn.execute(
            text("UPDATE rbac_permission SET code = :old_code WHERE code = :new_code"),
            {"old_code": _OLD_PERMISSION, "new_code": _NEW_PERMISSION},
        )
    new_role = conn.execute(
        text("SELECT id FROM rbac_role WHERE code = :code"),
        {"code": _NEW_ROLE},
    ).fetchone()
    old_role = conn.execute(
        text("SELECT id FROM rbac_role WHERE code = :code"),
        {"code": _OLD_ROLE},
    ).fetchone()
    if new_role and not old_role:
        conn.execute(
            text("UPDATE rbac_role SET code = :old_code WHERE code = :new_code"),
            {"old_code": _OLD_ROLE, "new_code": _NEW_ROLE},
        )
