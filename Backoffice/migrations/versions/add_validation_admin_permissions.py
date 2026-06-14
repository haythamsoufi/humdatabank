"""Add dedicated RBAC permissions for validation admin pages.

Revision ID: add_validation_admin_permissions
Revises: add_indicator_bank_history_area_label
Create Date: 2026-06-13

Splits validation dashboard, questions, and rules registry off from
admin.data_explore.compliance. Users/roles that had compliance access
receive the new validation permissions so existing access is preserved.
"""

from alembic import op
from sqlalchemy import text

revision = "add_validation_admin_permissions"
down_revision = "add_indicator_bank_history_area_label"
branch_labels = None
depends_on = None

NEW_PERMISSIONS = [
    (
        "admin.validation.dashboard",
        "Validation: Dashboard",
        "Access the Validation Dashboard (tracker, checks, dispatch)",
    ),
    (
        "admin.validation.questions",
        "Validation: Questions",
        "Manage validation questions (list, edit, import/export)",
    ),
    (
        "admin.validation.rules",
        "Validation: Rules",
        "Manage the Validation Rules Registry (thresholds, check types, templates)",
    ),
]

NEW_ROLES = [
    (
        "admin_validation_dashboard",
        "Admin: Validation Dashboard (Access)",
        "Access the Validation Dashboard (tracker, checks, dispatch).",
        "admin.validation.dashboard",
    ),
    (
        "admin_validation_questions",
        "Admin: Validation Questions (Manage)",
        "Manage validation questions (list, edit, import/export).",
        "admin.validation.questions",
    ),
    (
        "admin_validation_rules",
        "Admin: Validation Rules (Manage)",
        "Manage the Validation Rules Registry (thresholds, check types, templates).",
        "admin.validation.rules",
    ),
]

COMPLIANCE_ROLE_CODE = "admin_data_explorer_compliance"
COMPLIANCE_PERMISSION_CODE = "admin.data_explore.compliance"


def _ensure_permission(conn, code, name, description):
    row = conn.execute(
        text("SELECT id FROM rbac_permission WHERE code = :code"),
        {"code": code},
    ).fetchone()
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
    return conn.execute(
        text("SELECT id FROM rbac_permission WHERE code = :code"),
        {"code": code},
    ).fetchone()[0]


def _ensure_role(conn, role_code, role_name, role_desc):
    row = conn.execute(
        text("SELECT id FROM rbac_role WHERE code = :code"),
        {"code": role_code},
    ).fetchone()
    if row:
        return row[0]
    conn.execute(
        text(
            """
            INSERT INTO rbac_role (code, name, description, created_at)
            VALUES (:code, :name, :description, CURRENT_TIMESTAMP)
            """
        ),
        {"code": role_code, "name": role_name, "description": role_desc},
    )
    return conn.execute(
        text("SELECT id FROM rbac_role WHERE code = :code"),
        {"code": role_code},
    ).fetchone()[0]


def _link_role_permission(conn, role_id, permission_id):
    conn.execute(
        text(
            """
            INSERT INTO rbac_role_permission (role_id, permission_id, created_at)
            VALUES (:role_id, :perm_id, CURRENT_TIMESTAMP)
            ON CONFLICT DO NOTHING
            """
        ),
        {"role_id": role_id, "perm_id": permission_id},
    )


def _assign_role_to_users(conn, source_role_id, target_role_id):
    user_rows = conn.execute(
        text("SELECT user_id FROM rbac_user_role WHERE role_id = :role_id"),
        {"role_id": source_role_id},
    ).fetchall()
    for (user_id,) in user_rows:
        conn.execute(
            text(
                """
                INSERT INTO rbac_user_role (user_id, role_id, created_at)
                VALUES (:user_id, :role_id, CURRENT_TIMESTAMP)
                ON CONFLICT DO NOTHING
                """
            ),
            {"user_id": user_id, "role_id": target_role_id},
        )


def upgrade():
    conn = op.get_bind()

    permission_ids = {}
    for code, name, description in NEW_PERMISSIONS:
        permission_ids[code] = _ensure_permission(conn, code, name, description)

    role_ids = {}
    for role_code, role_name, role_desc, perm_code in NEW_ROLES:
        role_id = _ensure_role(conn, role_code, role_name, role_desc)
        role_ids[role_code] = role_id
        _link_role_permission(conn, role_id, permission_ids[perm_code])
        conn.execute(
            text(
                """
                UPDATE rbac_role
                SET name = :name, description = :description
                WHERE code = :code
                """
            ),
            {"code": role_code, "name": role_name, "description": role_desc},
        )

    compliance_role = conn.execute(
        text("SELECT id FROM rbac_role WHERE code = :code"),
        {"code": COMPLIANCE_ROLE_CODE},
    ).fetchone()
    if compliance_role:
        compliance_role_id = compliance_role[0]
        for role_code in role_ids:
            _assign_role_to_users(conn, compliance_role_id, role_ids[role_code])

    compliance_perm = conn.execute(
        text("SELECT id FROM rbac_permission WHERE code = :code"),
        {"code": COMPLIANCE_PERMISSION_CODE},
    ).fetchone()
    if compliance_perm:
        compliance_perm_id = compliance_perm[0]
        for perm_code, perm_id in permission_ids.items():
            rows = conn.execute(
                text(
                    """
                    SELECT role_id
                    FROM rbac_role_permission
                    WHERE permission_id = :perm_id
                    """
                ),
                {"perm_id": compliance_perm_id},
            ).fetchall()
            for (role_id,) in rows:
                _link_role_permission(conn, role_id, perm_id)


def downgrade():
    conn = op.get_bind()

    perm_codes = [code for code, _, _ in NEW_PERMISSIONS]
    role_codes = [role_code for role_code, _, _, _ in NEW_ROLES]

    perm_ids = []
    for code in perm_codes:
        row = conn.execute(
            text("SELECT id FROM rbac_permission WHERE code = :code"),
            {"code": code},
        ).fetchone()
        if row:
            perm_ids.append(row[0])

    role_ids = []
    for code in role_codes:
        row = conn.execute(
            text("SELECT id FROM rbac_role WHERE code = :code"),
            {"code": code},
        ).fetchone()
        if row:
            role_ids.append(row[0])

    for role_id in role_ids:
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

    for perm_id in perm_ids:
        conn.execute(
            text("DELETE FROM rbac_role_permission WHERE permission_id = :perm_id"),
            {"perm_id": perm_id},
        )
        conn.execute(
            text("DELETE FROM rbac_permission WHERE id = :perm_id"),
            {"perm_id": perm_id},
        )
