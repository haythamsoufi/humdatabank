"""Add report builder RBAC permissions and backfill from data explorer analysis."""

from alembic import op
from sqlalchemy import text

revision = "add_reports_permissions"
down_revision = "add_report_definition_table"
branch_labels = None
depends_on = None

PERMISSIONS = (
    ("admin.reports.view", "Reports: View", "View reports within assigned scope"),
    ("admin.reports.edit", "Reports: Edit", "Create and edit own reports"),
    ("admin.reports.manage", "Reports: Manage all", "View and edit all reports (system managers)"),
)

ROLES = (
    (
        "admin_reports_viewer",
        "Admin: Reports (View)",
        "View published reports within scope.",
        ("admin.reports.view",),
    ),
    (
        "admin_reports_editor",
        "Admin: Reports (Edit)",
        "Create and edit reports within scope.",
        ("admin.reports.view", "admin.reports.edit"),
    ),
)


def _ensure_permission(conn, code, name, description):
    row = conn.execute(text("SELECT id FROM rbac_permission WHERE code = :code"), {"code": code}).fetchone()
    if row:
        return row[0]
    conn.execute(
        text(
            """
            INSERT INTO rbac_permission (code, name, description, created_at)
            VALUES (:code, :name, :description, CURRENT_TIMESTAMP)
            """
        ),
        {"code": code, "name": name, "description": description},
    )
    return conn.execute(text("SELECT id FROM rbac_permission WHERE code = :code"), {"code": code}).fetchone()[0]


def _ensure_role(conn, code, name, description, perm_codes):
    row = conn.execute(text("SELECT id FROM rbac_role WHERE code = :code"), {"code": code}).fetchone()
    if not row:
        conn.execute(
            text(
                """
                INSERT INTO rbac_role (code, name, description, created_at)
                VALUES (:code, :name, :description, CURRENT_TIMESTAMP)
                """
            ),
            {"code": code, "name": name, "description": description},
        )
        row = conn.execute(text("SELECT id FROM rbac_role WHERE code = :code"), {"code": code}).fetchone()
    role_id = row[0]
    for perm_code in perm_codes:
        perm = conn.execute(text("SELECT id FROM rbac_permission WHERE code = :code"), {"code": perm_code}).fetchone()
        if perm:
            conn.execute(
                text(
                    """
                    INSERT INTO rbac_role_permission (role_id, permission_id, created_at)
                    VALUES (:role_id, :perm_id, CURRENT_TIMESTAMP)
                    ON CONFLICT DO NOTHING
                    """
                ),
                {"role_id": role_id, "perm_id": perm[0]},
            )


def upgrade():
    conn = op.get_bind()
    for code, name, description in PERMISSIONS:
        _ensure_permission(conn, code, name, description)
    for role_code, role_name, role_desc, perm_codes in ROLES:
        _ensure_role(conn, role_code, role_name, role_desc, perm_codes)

    analysis_perm = conn.execute(
        text("SELECT id FROM rbac_permission WHERE code = 'admin.data_explore.analysis'")
    ).fetchone()
    editor_perm = conn.execute(
        text("SELECT id FROM rbac_permission WHERE code = 'admin.reports.edit'")
    ).fetchone()
    viewer_perm = conn.execute(
        text("SELECT id FROM rbac_permission WHERE code = 'admin.reports.view'")
    ).fetchone()
    if analysis_perm and editor_perm and viewer_perm:
        role = conn.execute(
            text("SELECT id FROM rbac_role WHERE code = 'admin_data_explorer_analysis'")
        ).fetchone()
        if role:
            for perm_id in (viewer_perm[0], editor_perm[0]):
                conn.execute(
                    text(
                        """
                        INSERT INTO rbac_role_permission (role_id, permission_id, created_at)
                        VALUES (:role_id, :perm_id, CURRENT_TIMESTAMP)
                        ON CONFLICT DO NOTHING
                        """
                    ),
                    {"role_id": role[0], "perm_id": perm_id},
                )


def downgrade():
    conn = op.get_bind()
    codes = [p[0] for p in PERMISSIONS]
    for role_code, _, _, _ in ROLES:
        role = conn.execute(text("SELECT id FROM rbac_role WHERE code = :code"), {"code": role_code}).fetchone()
        if role:
            conn.execute(text("DELETE FROM rbac_user_role WHERE role_id = :id"), {"id": role[0]})
            conn.execute(text("DELETE FROM rbac_role_permission WHERE role_id = :id"), {"id": role[0]})
            conn.execute(text("DELETE FROM rbac_role WHERE id = :id"), {"id": role[0]})
    for code in codes:
        perm = conn.execute(text("SELECT id FROM rbac_permission WHERE code = :code"), {"code": code}).fetchone()
        if perm:
            conn.execute(text("DELETE FROM rbac_role_permission WHERE permission_id = :id"), {"id": perm[0]})
            conn.execute(text("DELETE FROM rbac_permission WHERE id = :id"), {"id": perm[0]})
