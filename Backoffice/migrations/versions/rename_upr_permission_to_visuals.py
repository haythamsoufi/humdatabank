"""Rename the UPR Visuals permission and role codes.

Revision ID: rename_upr_perm_visuals
Revises: add_template_version_integrity
Create Date: 2026-10-13

The Data Explorer tab is UPR Visuals. Its permission and role codes follow that
name. Existing grants stay attached: rows are renamed in place, or merged when
a seed has already created the new code.
"""

from alembic import op
from sqlalchemy import text

revision = "rename_upr_perm_visuals"
down_revision = "add_template_version_integrity"
branch_labels = None
depends_on = None

_OLD_PERMISSION = "admin.data_explore.upr"
_NEW_PERMISSION = "admin.data_explore.upr_visuals"
_OLD_ROLE = "admin_data_explorer_upr"
_NEW_ROLE = "admin_data_explorer_upr_visuals"
_PERMISSION_NAME = "Data Explorer: UPR Visuals"
_PERMISSION_DESCRIPTION = "Access UPR Visuals in Data Explorer"
_ROLE_NAME = "Admin: Data Explorer (UPR Visuals)"
_ROLE_DESCRIPTION = "Access UPR Visuals in Data Explorer."
_OLD_PERMISSION_NAME = "Data Explorer: UPR"
_OLD_PERMISSION_DESCRIPTION = "Access Unified Plan and Report visuals in Data Explorer"
_OLD_ROLE_NAME = "Admin: Data Explorer (UPR)"
_OLD_ROLE_DESCRIPTION = "Access Unified Plan and Report visuals in Data Explorer."


def _rename_permission(conn, old_code: str, new_code: str, name: str, description: str) -> None:
    old = conn.execute(
        text("SELECT id FROM rbac_permission WHERE code = :code"),
        {"code": old_code},
    ).fetchone()
    if not old:
        return
    new = conn.execute(
        text("SELECT id FROM rbac_permission WHERE code = :code"),
        {"code": new_code},
    ).fetchone()
    if new:
        conn.execute(
            text(
                """
                DELETE FROM rbac_role_permission
                WHERE permission_id = :old_id
                  AND role_id IN (
                      SELECT role_id FROM rbac_role_permission WHERE permission_id = :new_id
                  )
                """
            ),
            {"new_id": new[0], "old_id": old[0]},
        )
        conn.execute(
            text("UPDATE rbac_role_permission SET permission_id = :new_id WHERE permission_id = :old_id"),
            {"new_id": new[0], "old_id": old[0]},
        )
        conn.execute(text("DELETE FROM rbac_permission WHERE id = :perm_id"), {"perm_id": old[0]})
        conn.execute(
            text(
                """
                UPDATE rbac_permission
                SET name = :name, description = :description
                WHERE id = :perm_id
                """
            ),
            {"perm_id": new[0], "name": name, "description": description},
        )
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
            "old_code": old_code,
            "new_code": new_code,
            "name": name,
            "description": description,
        },
    )


def _rename_role(conn, old_code: str, new_code: str, name: str, description: str) -> None:
    old = conn.execute(
        text("SELECT id FROM rbac_role WHERE code = :code"),
        {"code": old_code},
    ).fetchone()
    if not old:
        return
    new = conn.execute(
        text("SELECT id FROM rbac_role WHERE code = :code"),
        {"code": new_code},
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
        conn.execute(
            text(
                """
                UPDATE rbac_role
                SET name = :name, description = :description
                WHERE id = :role_id
                """
            ),
            {"role_id": new[0], "name": name, "description": description},
        )
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
            "old_code": old_code,
            "new_code": new_code,
            "name": name,
            "description": description,
        },
    )


def upgrade():
    conn = op.get_bind()
    _rename_permission(
        conn,
        _OLD_PERMISSION,
        _NEW_PERMISSION,
        _PERMISSION_NAME,
        _PERMISSION_DESCRIPTION,
    )
    _rename_role(conn, _OLD_ROLE, _NEW_ROLE, _ROLE_NAME, _ROLE_DESCRIPTION)


def downgrade():
    conn = op.get_bind()
    _rename_permission(
        conn,
        _NEW_PERMISSION,
        _OLD_PERMISSION,
        _OLD_PERMISSION_NAME,
        _OLD_PERMISSION_DESCRIPTION,
    )
    _rename_role(conn, _NEW_ROLE, _OLD_ROLE, _OLD_ROLE_NAME, _OLD_ROLE_DESCRIPTION)
