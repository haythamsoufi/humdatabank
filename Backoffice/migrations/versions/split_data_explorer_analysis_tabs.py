"""Give Disaggregation, Service income, and Everyone Counts their own permissions.

Those Explore Data tabs shared admin.data_explore.analysis. This migration:

1. Creates one permission and one user-form role per tab.
2. Copies the legacy Analysis grant onto those permissions for every role that
   already had it (Admin: Full, System Manager, custom roles).
3. Assigns the three new roles to users who had Admin: Data Explorer (Analysis).
4. Removes that shared role so the user form no longer shows an Analysis
   checkbox that is not a tab.

The legacy permission row stays so existing links remain valid.
"""

from alembic import op
from sqlalchemy import text

revision = "split_explore_analysis_tabs"
down_revision = "backfill_t22_matrix_keys"
branch_labels = None
depends_on = None

_LEGACY_ROLE = "admin_data_explorer_analysis"
_LEGACY_PERMISSION = "admin.data_explore.analysis"

_NEW_TABS = (
    (
        "admin.data_explore.disaggregation",
        "Data Explorer: Disaggregation Analysis",
        "Access the Disaggregation Analysis tab in Data Explorer",
        "admin_data_explorer_disaggregation",
        "Admin: Data Explorer (Disaggregation Analysis)",
        "Access the Disaggregation Analysis tab in Data Explorer.",
    ),
    (
        "admin.data_explore.service_income",
        "Data Explorer: Service income",
        "Access the Service income tab in Data Explorer",
        "admin_data_explorer_service_income",
        "Admin: Data Explorer (Service income)",
        "Access the Service income tab in Data Explorer.",
    ),
    (
        "admin.data_explore.everyone_counts",
        "Data Explorer: Everyone Counts",
        "Access the Everyone Counts tab in Data Explorer",
        "admin_data_explorer_everyone_counts",
        "Admin: Data Explorer (Everyone Counts)",
        "Access the Everyone Counts tab in Data Explorer.",
    ),
)


def _ensure_permission(conn, code: str, name: str, description: str) -> int:
    row = conn.execute(
        text("SELECT id FROM rbac_permission WHERE code = :code"),
        {"code": code},
    ).fetchone()
    if row:
        conn.execute(
            text(
                """
                UPDATE rbac_permission
                SET name = :name, description = :description
                WHERE code = :code
                """
            ),
            {"code": code, "name": name, "description": description},
        )
        return int(row[0])
    conn.execute(
        text(
            """
            INSERT INTO rbac_permission (code, name, description, created_at)
            VALUES (:code, :name, :description, CURRENT_TIMESTAMP)
            """
        ),
        {"code": code, "name": name, "description": description},
    )
    created = conn.execute(
        text("SELECT id FROM rbac_permission WHERE code = :code"),
        {"code": code},
    ).fetchone()
    return int(created[0])


def _ensure_role(conn, code: str, name: str, description: str, permission_id: int) -> int:
    row = conn.execute(
        text("SELECT id FROM rbac_role WHERE code = :code"),
        {"code": code},
    ).fetchone()
    if row:
        role_id = int(row[0])
        conn.execute(
            text(
                """
                UPDATE rbac_role
                SET name = :name, description = :description
                WHERE id = :role_id
                """
            ),
            {"role_id": role_id, "name": name, "description": description},
        )
    else:
        conn.execute(
            text(
                """
                INSERT INTO rbac_role (code, name, description, created_at)
                VALUES (:code, :name, :description, CURRENT_TIMESTAMP)
                """
            ),
            {"code": code, "name": name, "description": description},
        )
        role_id = int(
            conn.execute(
                text("SELECT id FROM rbac_role WHERE code = :code"),
                {"code": code},
            ).fetchone()[0]
        )
    conn.execute(
        text(
            """
            INSERT INTO rbac_role_permission (role_id, permission_id, created_at)
            VALUES (:role_id, :permission_id, CURRENT_TIMESTAMP)
            ON CONFLICT DO NOTHING
            """
        ),
        {"role_id": role_id, "permission_id": permission_id},
    )
    return role_id


def upgrade():
    conn = op.get_bind()

    new_permission_ids = []
    new_role_ids = []
    for perm_code, perm_name, perm_desc, role_code, role_name, role_desc in _NEW_TABS:
        permission_id = _ensure_permission(conn, perm_code, perm_name, perm_desc)
        role_id = _ensure_role(conn, role_code, role_name, role_desc, permission_id)
        new_permission_ids.append(permission_id)
        new_role_ids.append(role_id)

    legacy_permission = conn.execute(
        text("SELECT id FROM rbac_permission WHERE code = :code"),
        {"code": _LEGACY_PERMISSION},
    ).fetchone()
    if legacy_permission:
        conn.execute(
            text(
                """
                UPDATE rbac_permission
                SET name = 'Data Explorer: Analysis (legacy)',
                    description = 'Legacy grant. Disaggregation, Service income, and Everyone Counts each have their own permission.'
                WHERE id = :permission_id
                """
            ),
            {"permission_id": int(legacy_permission[0])},
        )
        for permission_id in new_permission_ids:
            conn.execute(
                text(
                    """
                    INSERT INTO rbac_role_permission (role_id, permission_id, created_at)
                    SELECT role_id, :permission_id, CURRENT_TIMESTAMP
                    FROM rbac_role_permission
                    WHERE permission_id = :legacy_permission_id
                    ON CONFLICT DO NOTHING
                    """
                ),
                {
                    "permission_id": permission_id,
                    "legacy_permission_id": int(legacy_permission[0]),
                },
            )

    legacy_role = conn.execute(
        text("SELECT id FROM rbac_role WHERE code = :code"),
        {"code": _LEGACY_ROLE},
    ).fetchone()
    if legacy_role:
        legacy_role_id = int(legacy_role[0])
        for role_id in new_role_ids:
            conn.execute(
                text(
                    """
                    INSERT INTO rbac_user_role (user_id, role_id, created_at)
                    SELECT user_id, :role_id, CURRENT_TIMESTAMP
                    FROM rbac_user_role
                    WHERE role_id = :legacy_role_id
                    ON CONFLICT DO NOTHING
                    """
                ),
                {"role_id": role_id, "legacy_role_id": legacy_role_id},
            )
        conn.execute(
            text("DELETE FROM rbac_user_role WHERE role_id = :role_id"),
            {"role_id": legacy_role_id},
        )
        conn.execute(
            text("DELETE FROM rbac_role_permission WHERE role_id = :role_id"),
            {"role_id": legacy_role_id},
        )
        conn.execute(
            text("DELETE FROM rbac_role WHERE id = :role_id"),
            {"role_id": legacy_role_id},
        )


def downgrade():
    conn = op.get_bind()

    legacy_permission = conn.execute(
        text("SELECT id FROM rbac_permission WHERE code = :code"),
        {"code": _LEGACY_PERMISSION},
    ).fetchone()
    if not legacy_permission:
        return
    legacy_permission_id = int(legacy_permission[0])

    legacy_role = conn.execute(
        text("SELECT id FROM rbac_role WHERE code = :code"),
        {"code": _LEGACY_ROLE},
    ).fetchone()
    if not legacy_role:
        conn.execute(
            text(
                """
                INSERT INTO rbac_role (code, name, description, created_at)
                VALUES (
                    :code,
                    'Admin: Data Explorer (Analysis)',
                    'Access the Analysis tab in Data Explorer.',
                    CURRENT_TIMESTAMP
                )
                """
            ),
            {"code": _LEGACY_ROLE},
        )
        legacy_role = conn.execute(
            text("SELECT id FROM rbac_role WHERE code = :code"),
            {"code": _LEGACY_ROLE},
        ).fetchone()
    legacy_role_id = int(legacy_role[0])
    conn.execute(
        text(
            """
            INSERT INTO rbac_role_permission (role_id, permission_id, created_at)
            VALUES (:role_id, :permission_id, CURRENT_TIMESTAMP)
            ON CONFLICT DO NOTHING
            """
        ),
        {"role_id": legacy_role_id, "permission_id": legacy_permission_id},
    )

    new_role_codes = [row[3] for row in _NEW_TABS]
    for role_code in new_role_codes:
        row = conn.execute(
            text("SELECT id FROM rbac_role WHERE code = :code"),
            {"code": role_code},
        ).fetchone()
        if not row:
            continue
        conn.execute(
            text(
                """
                INSERT INTO rbac_user_role (user_id, role_id, created_at)
                SELECT user_id, :legacy_role_id, CURRENT_TIMESTAMP
                FROM rbac_user_role
                WHERE role_id = :role_id
                ON CONFLICT DO NOTHING
                """
            ),
            {"legacy_role_id": legacy_role_id, "role_id": int(row[0])},
        )

    for perm_code, _perm_name, _perm_desc, role_code, _role_name, _role_desc in _NEW_TABS:
        role = conn.execute(
            text("SELECT id FROM rbac_role WHERE code = :code"),
            {"code": role_code},
        ).fetchone()
        if role:
            role_id = int(role[0])
            conn.execute(text("DELETE FROM rbac_user_role WHERE role_id = :id"), {"id": role_id})
            conn.execute(text("DELETE FROM rbac_role_permission WHERE role_id = :id"), {"id": role_id})
            conn.execute(text("DELETE FROM rbac_role WHERE id = :id"), {"id": role_id})
        perm = conn.execute(
            text("SELECT id FROM rbac_permission WHERE code = :code"),
            {"code": perm_code},
        ).fetchone()
        if perm:
            perm_id = int(perm[0])
            conn.execute(
                text("DELETE FROM rbac_role_permission WHERE permission_id = :id"),
                {"id": perm_id},
            )
            conn.execute(text("DELETE FROM rbac_permission WHERE id = :id"), {"id": perm_id})
