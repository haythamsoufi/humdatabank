"""Rename admin.notifications.manage RBAC permission to admin.communication.manage

Revision ID: rename_notif_rbac_comm
Revises: add_email_delivery_cancelled
Create Date: 2026-06-29
"""

from alembic import op
from sqlalchemy import text

revision = "rename_notif_rbac_comm"
down_revision = "add_email_delivery_cancelled"
branch_labels = None
depends_on = None

_OLD_PERMISSION = "admin.notifications.manage"
_NEW_PERMISSION = "admin.communication.manage"
_OLD_ROLE = "admin_notifications_manager"
_NEW_ROLE = "admin_communication_manager"

_PERMISSION_NAME = "Manage communication"
_PERMISSION_DESCRIPTION = (
    "Manage admin Communication Center (view all communications and send)"
)
_ROLE_NAME = "Admin: Communication (Manage)"
_ROLE_DESCRIPTION = (
    "Manage admin Communication Center (view all communications and send "
    "notifications, email, and push)."
)


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
        # Both exist (partial deploy): keep the new row and drop the old one.
        conn.execute(
            text(
                "DELETE FROM rbac_role_permission WHERE permission_id = :perm_id"
            ),
            {"perm_id": old[0]},
        )
        conn.execute(
            text("DELETE FROM rbac_access_grant WHERE permission_id = :perm_id"),
            {"perm_id": old[0]},
        )
        conn.execute(
            text("DELETE FROM rbac_permission WHERE id = :perm_id"),
            {"perm_id": old[0]},
        )
        conn.execute(
            text(
                """
                UPDATE rbac_permission
                SET name = :name, description = :description
                WHERE id = :perm_id
                """
            ),
            {
                "perm_id": new[0],
                "name": _PERMISSION_NAME,
                "description": _PERMISSION_DESCRIPTION,
            },
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
        old_role_id = old[0]
        new_role_id = new[0]
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
            {"old_role_id": old_role_id, "new_role_id": new_role_id},
        )
        conn.execute(
            text("DELETE FROM rbac_user_role WHERE role_id = :role_id"),
            {"role_id": old_role_id},
        )
        conn.execute(
            text("DELETE FROM rbac_role_permission WHERE role_id = :role_id"),
            {"role_id": old_role_id},
        )
        conn.execute(
            text("DELETE FROM rbac_role WHERE id = :role_id"),
            {"role_id": old_role_id},
        )
        conn.execute(
            text(
                """
                UPDATE rbac_role
                SET name = :name, description = :description
                WHERE id = :role_id
                """
            ),
            {
                "role_id": new_role_id,
                "name": _ROLE_NAME,
                "description": _ROLE_DESCRIPTION,
            },
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


def downgrade():
    conn = op.get_bind()

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
            text(
                """
                UPDATE rbac_permission
                SET code = :old_code,
                    name = 'Manage notifications',
                    description = 'Manage admin notifications center (view/send)'
                WHERE code = :new_code
                """
            ),
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
            text(
                """
                UPDATE rbac_role
                SET code = :old_code,
                    name = 'Admin: Notifications (Manage)',
                    description = (
                        'Manage admin notifications center '
                        '(view all notifications and send notifications).'
                    )
                WHERE code = :new_code
                """
            ),
            {"old_code": _OLD_ROLE, "new_code": _NEW_ROLE},
        )
