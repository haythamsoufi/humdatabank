"""Add P&B Progress permission for the Data Explorer tab."""

from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = "add_pb_progress_permission"
down_revision = "add_user_preferred_language"
branch_labels = None
depends_on = None


def _rename_legacy_gb_report(conn):
    """Rename legacy GB Report permission/role if a prior migration was applied."""
    conn.execute(
        text(
            """
            UPDATE rbac_permission
            SET code = 'admin.data_explore.pb_progress',
                name = 'Data Explorer: P&B Progress',
                description = 'Access the Plan and Budget progress tab in Data Explorer'
            WHERE code = 'admin.data_explore.gb_report'
            """
        )
    )
    conn.execute(
        text(
            """
            UPDATE rbac_role
            SET code = 'admin_data_explorer_pb_progress',
                name = 'Admin: Data Explorer (P&B Progress)',
                description = 'Access the Plan and Budget progress tab in Data Explorer.'
            WHERE code = 'admin_data_explorer_gb_report'
            """
        )
    )


def upgrade():
    conn = op.get_bind()
    _rename_legacy_gb_report(conn)

    permission = (
        "admin.data_explore.pb_progress",
        "Data Explorer: P&B Progress",
        "Access the Plan and Budget progress tab in Data Explorer",
    )
    role = (
        "admin_data_explorer_pb_progress",
        "Admin: Data Explorer (P&B Progress)",
        "Access the Plan and Budget progress tab in Data Explorer.",
        "admin.data_explore.pb_progress",
    )

    code, name, description = permission
    result = conn.execute(
        text("SELECT id FROM rbac_permission WHERE code = :code"),
        {"code": code},
    ).fetchone()
    if not result:
        conn.execute(
            text(
                """
                INSERT INTO rbac_permission (code, name, description, created_at)
                VALUES (:code, :name, :description, CURRENT_TIMESTAMP)
                """
            ),
            {"code": code, "name": name, "description": description},
        )

    role_code, role_name, role_desc, perm_code = role
    result = conn.execute(
        text("SELECT id FROM rbac_role WHERE code = :code"),
        {"code": role_code},
    ).fetchone()
    if not result:
        conn.execute(
            text(
                """
                INSERT INTO rbac_role (code, name, description, created_at)
                VALUES (:code, :name, :description, CURRENT_TIMESTAMP)
                """
            ),
            {"code": role_code, "name": role_name, "description": role_desc},
        )

        role_result = conn.execute(
            text("SELECT id FROM rbac_role WHERE code = :code"),
            {"code": role_code},
        ).fetchone()
        perm_result = conn.execute(
            text("SELECT id FROM rbac_permission WHERE code = :code"),
            {"code": perm_code},
        ).fetchone()
        if role_result and perm_result:
            conn.execute(
                text(
                    """
                    INSERT INTO rbac_role_permission (role_id, permission_id, created_at)
                    VALUES (:role_id, :perm_id, CURRENT_TIMESTAMP)
                    ON CONFLICT DO NOTHING
                    """
                ),
                {"role_id": role_result[0], "perm_id": perm_result[0]},
            )


def downgrade():
    conn = op.get_bind()

    role_code = "admin_data_explorer_pb_progress"
    perm_code = "admin.data_explore.pb_progress"

    role = conn.execute(
        text("SELECT id FROM rbac_role WHERE code = :code"),
        {"code": role_code},
    ).fetchone()
    if role:
        role_id = role[0]
        conn.execute(
            text("DELETE FROM rbac_user_role WHERE role_id = :role_id"),
            {"role_id": role_id},
        )
        conn.execute(
            text("DELETE FROM rbac_role_permission WHERE role_id = :role_id"),
            {"role_id": role_id},
        )
        conn.execute(
            text("DELETE FROM rbac_role WHERE id = :role_id"),
            {"role_id": role_id},
        )

    perm = conn.execute(
        text("SELECT id FROM rbac_permission WHERE code = :code"),
        {"code": perm_code},
    ).fetchone()
    if perm:
        perm_id = perm[0]
        conn.execute(
            text("DELETE FROM rbac_role_permission WHERE permission_id = :perm_id"),
            {"perm_id": perm_id},
        )
        conn.execute(
            text("DELETE FROM rbac_permission WHERE id = :perm_id"),
            {"perm_id": perm_id},
        )
